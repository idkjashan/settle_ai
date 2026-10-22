import asyncio
import json
import uuid
from pathlib import Path
from typing import Optional, List, Union, Any, Dict
from fastapi import APIRouter, Depends, File, Form, UploadFile, BackgroundTasks, HTTPException, Response, status
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.session import get_db_session
from app.infrastructure.db.repositories import PolicyRepository, ClaimRepository
from app.infrastructure.cache.redis_manager import redis_manager
from app.infrastructure.storage.scratch_ingest import scratch_ingest_service
from app.infrastructure.storage.s3_client import s3_client
from app.domain.fast_fail_gate.schemas import (
    CaptureSource,
    CaptureModality,
    FastFailResponseDTO,
    FastFailFailureCode,
)
from app.domain.fast_fail_gate.policy_dedupe_gate import PolicyAndDedupeGate
from app.domain.fast_fail_gate.container_forensics import container_forensics_validator
from app.domain.fast_fail_gate.visual_quality_gate import visual_quality_validator
from app.domain.fast_fail_gate.remediation_mapper import remediation_mapper
from app.domain.fast_fail_gate.orchestrator import FastFailGateOrchestrator
from app.domain.vehicle_identity_continuity.orchestrator import VehicleIdentityContinuityOrchestrator
from app.domain.vehicle_identity_continuity.cut_detector import cut_detector
from app.domain.vehicle_identity_continuity.plate_ocr_validator import plate_ocr_validator
from app.domain.vehicle_identity_continuity.color_grounding_validator import color_grounding_validator
from app.domain.vehicle_identity_continuity.object_tracker import object_tracker
from app.infrastructure.db.session import async_session_factory
from app.core.exceptions import PayloadTooLargeException, LockConflictException, AutoSettleException
from app.core.logging import logger
from app.domain.negotiation_chatbot.schemas import (
    ClaimantMessageDTO,
    OfferCardDTO,
    NegotiationTurnDTO,
    NegotiationSessionDTO,
)
from app.domain.settlement_escalation.schemas import (
    SettlementVoucherDTO,
    HumanAdjusterDossierDTO,
)


def extract_fallback_keyframes(scratch_path: Any, claim_id: uuid.UUID) -> Dict[str, str]:
    """Extracts fallback keyframes from video or photo pack so Stage 2 and Stage 3 always have valid frames."""
    kf_dir = Path("/tmp/autosettle_keyframes") / str(claim_id)
    kf_dir.mkdir(parents=True, exist_ok=True)
    saved: Dict[str, str] = {}

    if isinstance(scratch_path, (list, tuple)):
        import shutil
        for idx, p in enumerate(scratch_path, 1):
            if Path(p).exists():
                out_p = kf_dir / f"keyframe_{idx:02d}.jpg"
                try:
                    shutil.copyfile(str(p), str(out_p))
                    saved[f"keyframe_{idx:02d}"] = str(out_p)
                except Exception as e:
                    logger.warning(f"Failed copying photo keyframe {p}: {e}")
    elif scratch_path and Path(scratch_path).exists():
        import cv2
        cap = cv2.VideoCapture(str(scratch_path))
        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames > 0:
                sample_ratios = [0.1, 0.3, 0.5, 0.7, 0.9]
                for idx, r in enumerate(sample_ratios, 1):
                    f_no = min(int(total_frames * r), total_frames - 1)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, f_no)
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        out_p = kf_dir / f"keyframe_{idx:02d}.jpg"
                        cv2.imwrite(str(out_p), frame)
                        saved[f"keyframe_{idx:02d}"] = str(out_p)
        except Exception as cv_err:
            logger.warning(f"Error sampling keyframes from {scratch_path}: {cv_err}")
        finally:
            cap.release()

    if not saved:
        import numpy as np
        import cv2
        dummy = np.zeros((720, 1280, 3), dtype=np.uint8)
        out_p = kf_dir / "keyframe_01.jpg"
        cv2.imwrite(str(out_p), dummy)
        saved["keyframe_01"] = str(out_p)

    vals = list(saved.values())
    saved["front_bumper"] = vals[0]
    saved["side_body_panel"] = vals[min(1, len(vals) - 1)]
    saved["damage_closeup_primary"] = vals[min(2, len(vals) - 1)]
    return saved


async def run_stage1_pipeline_task(
    claim_id: uuid.UUID,
    scratch_path,
    policy_id: str,
    is_demo_rehearsal: bool,
    claim_description: Optional[str] = None,
    skip_stage_1: bool = False,
):
    """Background task executing Stage 1 (Vehicle Identity & Continuity Grounding)
    and handing off to Conditioned Stage 2 (Dual-Mask Segmentation).
    """
    try:
        claim_intent = None
        if claim_description and claim_description.strip():
            try:
                from app.domain.claim_intent.intent_grounder import get_claim_intent_grounder
                claim_intent = get_claim_intent_grounder().ground(claim_description)
                logger.info(
                    f"Grounded claim intent for {claim_id}: parts={claim_intent.claimed_parts}, "
                    f"damages={claim_intent.claimed_damages} in {claim_intent.extraction_latency_ms}ms"
                )
            except Exception as intent_err:
                logger.warning(f"Claim intent grounding failed for {claim_id}: {intent_err}")

        # Ensure fallback keyframes are extracted early while scratch_path is guaranteed available
        pre_extracted_kf = extract_fallback_keyframes(scratch_path, claim_id)

        async with async_session_factory() as db:
            policy_repo = PolicyRepository(db)
            claim_repo = ClaimRepository(db)
            stage1_orch = VehicleIdentityContinuityOrchestrator(
                policy_repo=policy_repo,
                claim_repo=claim_repo,
                redis_mgr=redis_manager,
                cut_det=cut_detector,
                plate_val=plate_ocr_validator,
                color_val=color_grounding_validator,
                tracker=object_tracker,
            )
            # Step 1: Execute Stage 1 (or bypass if skip_stage_1=True)
            stage1_passed = False
            telemetry = None

            if skip_stage_1:
                logger.info(f"[SKIP_STAGE_1] User requested bypass of Stage 1 checks for claim {claim_id}. Proceeding directly to Stage 2 & 3.")
                from app.domain.vehicle_identity_continuity.schemas import (
                    CutDetectionResult,
                    PlateValidationResult,
                    ColorValidationResult,
                    TrackingAndKeyframeResult,
                    VehicleContinuityTelemetryDTO,
                )
                telemetry = VehicleContinuityTelemetryDTO(
                    passed=True,
                    cut_report=CutDetectionResult(is_continuous=True),
                    plate_report=PlateValidationResult(is_verified=True, expected_plate="BYPASSED", extracted_plate="BYPASSED", ocr_confidence=1.0),
                    color_report=ColorValidationResult(is_color_match=True, expected_color_name="WHITE"),
                    tracking_report=TrackingAndKeyframeResult(is_persistent=True, saved_keyframes=pre_extracted_kf),
                    total_execution_ms=1.0,
                )
                stage1_passed = True
                await claim_repo.update_claim_stage(
                    claim_id=claim_id,
                    stage="STAGE_2_SEGMENTATION",
                    status="PROCESSING",
                    escalation_code=None,
                    failure_codes=None,
                )
                await redis_manager.publish_event(
                    claim_id=claim_id,
                    event_name="STAGE_1_PASSED",
                    payload={
                        "claim_id": str(claim_id),
                        "status": "PROCESSING",
                        "stage": "STAGE_2_SEGMENTATION",
                        "note": "Stage 1 checks bypassed by user flag for model testing",
                    },
                )
            else:
                try:
                    if isinstance(scratch_path, (list, tuple)):
                        telemetry = await stage1_orch.execute_photo_pack(
                            claim_id=claim_id,
                            photo_paths=list(scratch_path),
                            policy_id=policy_id,
                            is_demo_rehearsal=is_demo_rehearsal,
                        )
                    else:
                        telemetry = await stage1_orch.execute(
                            claim_id=claim_id,
                            scratch_video_path=scratch_path,
                            policy_id=policy_id,
                            is_demo_rehearsal=is_demo_rehearsal,
                        )
                    stage1_passed = bool(telemetry and telemetry.passed)
                    logger.info(f"Stage 1 background execution complete for {claim_id}: passed={stage1_passed}")
                except Exception as e:
                    logger.error(f"Stage 1 background execution failed for {claim_id}: {e}", exc_info=True)
                    # ponytail: mark claim REJECTED_STAGE1_ERROR so it never hangs in PROCESSING state
                    try:
                        await claim_repo.update_claim_stage(
                            claim_id=claim_id,
                            stage="STAGE_1_IDENTITY",
                            status="REJECTED_STAGE1_ERROR",
                            escalation_code="ESC-02",
                            failure_codes=["STAGE_1_INTERNAL_ERROR"],
                        )
                        await redis_manager.publish_event(
                            claim_id=claim_id,
                            event_name="STAGE_1_FAILED",
                            payload={
                                "claim_id": str(claim_id),
                                "status": "REJECTED_STAGE1_ERROR",
                                "escalation_code": "ESC-02",
                                "failure_codes": ["STAGE_1_INTERNAL_ERROR"],
                            },
                        )
                    except Exception as db_err:
                        logger.critical(f"Failed to record stage 1 crash in DB for {claim_id}: {db_err}")
                    return

            # Step 2: Handoff to Stage 2 (Dual-Mask Segmentation)
            saved_kf = getattr(telemetry.tracking_report, "saved_keyframes", None) if telemetry else None
            saved_kf = saved_kf or pre_extracted_kf
            if stage1_passed and telemetry and saved_kf:
                logger.info(f"Handoff to Stage 2 Dual-Mask Segmentation for claim {claim_id}...")
                from app.domain.vehicle_identity_continuity.schemas import Stage2HandoffPayload
                from app.domain.dual_mask_segmentation.orchestrator import get_stage2_orchestrator
                from app.domain.dual_mask_segmentation.exceptions import (
                    Stage2Error,
                    Stage2ModelCompatibilityError,
                )

                try:
                    redis_client = await redis_manager.get_client()
                except Exception:
                    redis_client = None

                try:
                    ref_video_path = str(scratch_path[0]) if isinstance(scratch_path, (list, tuple)) and scratch_path else str(scratch_path)
                    all_kf = {k: str(v) for k, v in saved_kf.items()}
                    for i, p_str in enumerate(getattr(telemetry.tracking_report, "curated_keyframes", []) or [], 1):
                        all_kf.setdefault(f"keyframe_{i:02d}", str(p_str))

                    stage2_payload = Stage2HandoffPayload(
                        claim_id=claim_id,
                        policy_id=policy_id,
                        scratch_video_path=ref_video_path,
                        keyframe_paths=all_kf,
                        vehicle_telemetry=telemetry,
                        claim_intent=claim_intent,
                    )
                    stage2_orch = get_stage2_orchestrator(
                        db_session=db,
                        redis_client=redis_client,
                    )
                    stage3_payload = await stage2_orch.execute(stage2_payload)
                    logger.info(
                        f"Stage 2 background execution complete for {claim_id}: "
                        f"{len(stage3_payload.grounded_parts)} parts grounded."
                    )

                    # Step 3: Handoff to Stage 3 (Set-of-Marks VLM Damage Inspection)
                    stage4_payload = None
                    if stage3_payload and getattr(stage3_payload, "grounded_parts", None):
                        logger.info(f"Handoff to Stage 3 VLM Damage Inspection for claim {claim_id}...")
                        from app.domain.vlm_damage_inspection.orchestrator import Stage3VLMOrchestrator
                        from app.domain.vlm_damage_inspection.exceptions import Stage3Error

                        try:
                            stage3_orch = Stage3VLMOrchestrator()
                            stage4_payload = await stage3_orch.inspect_claim(stage3_payload)
                            logger.info(
                                f"Stage 3 inspection complete for claim {claim_id}: "
                                f"{len(stage4_payload.verified_parts)} verified damaged parts."
                            )
                        except Stage3Error as s3e:
                            logger.warning(
                                f"Stage 3 domain escalation for claim {claim_id}: code={s3e.code}, message={s3e.message}"
                            )
                            return
                        except Exception as s3_err:
                            logger.error(f"Stage 3 unexpected execution failure for {claim_id}: {s3_err}", exc_info=True)
                            try:
                                await claim_repo.update_claim_stage(
                                    claim_id=claim_id,
                                    stage="STAGE_3_VLM_INSPECTION",
                                    status="REJECTED_STAGE3_ERROR",
                                    escalation_code="ESC-07",
                                    failure_codes=["STAGE_3_INTERNAL_ERROR"],
                                )
                                await redis_manager.publish_event(
                                    claim_id=claim_id,
                                    event_name="STAGE_3_FAILED",
                                    payload={
                                        "claim_id": str(claim_id),
                                        "status": "REJECTED_STAGE3_ERROR",
                                        "failure_codes": ["STAGE_3_INTERNAL_ERROR"],
                                    },
                                )
                            except Exception as db_err:
                                logger.critical(f"Failed to record stage 3 crash in DB for {claim_id}: {db_err}")
                            return

                    # Step 4: Handoff to Stage 4 (Actuarial Pricing Engine)
                    actuarial_estimate = None
                    if stage4_payload and getattr(stage4_payload, "verified_parts", None):
                        logger.info(f"Handoff to Stage 4 Actuarial Pricing Engine for claim {claim_id}...")
                        from app.domain.actuarial_pricing.orchestrator import Stage4ActuarialOrchestrator
                        from app.domain.actuarial_pricing.exceptions import ActuarialPricingError

                        try:
                            stage4_orch = Stage4ActuarialOrchestrator(
                                session=db,
                                redis_manager=redis_manager,
                            )
                            actuarial_estimate = await stage4_orch.execute(stage4_payload)
                            logger.info(
                                f"Stage 4 pricing complete for claim {claim_id}: "
                                f"gross repair ₹{actuarial_estimate.summary.gross_garage_repair_inr}, "
                                f"initial offer ₹{actuarial_estimate.settlement_band.initial_offer_inr}"
                            )
                        except ActuarialPricingError as s4e:
                            logger.warning(
                                f"Stage 4 actuarial escalation for claim {claim_id}: code={s4e.code}, message={s4e.message}"
                            )
                            return
                        except Exception as s4_err:
                            logger.error(f"Stage 4 unexpected execution failure for {claim_id}: {s4_err}", exc_info=True)
                            try:
                                await claim_repo.update_claim_stage(
                                    claim_id=claim_id,
                                    stage="STAGE_4_ACTUARIAL_PRICING",
                                    status="REJECTED_STAGE4_ERROR",
                                    escalation_code=None,
                                    failure_codes=["STAGE_4_INTERNAL_ERROR"],
                                )
                                await redis_manager.publish_event(
                                    claim_id=claim_id,
                                    event_name="STAGE_4_FAILED",
                                    payload={
                                        "claim_id": str(claim_id),
                                        "status": "REJECTED_STAGE4_ERROR",
                                        "failure_codes": ["STAGE_4_INTERNAL_ERROR"],
                                    },
                                )
                            except Exception as db_err:
                                logger.critical(f"Failed to record stage 4 crash in DB for {claim_id}: {db_err}")
                            return

                    # Step 5: Initialize Stage 5 (Negotiation Chatbot Session)
                    if actuarial_estimate and not getattr(actuarial_estimate, "is_ceiling_breached", False):
                        logger.info(f"Handoff to Stage 5 Negotiation Chatbot for claim {claim_id}...")
                        from app.domain.negotiation_chatbot.orchestrator import Stage5NegotiationOrchestrator

                        try:
                            stage5_orch = Stage5NegotiationOrchestrator(
                                db_session=db,
                                redis_mgr=redis_manager,
                            )
                            negotiation_session = await stage5_orch.initialize_session(actuarial_estimate)
                            logger.info(
                                f"Stage 5 negotiation session initialized for claim {claim_id}: "
                                f"initial offer ₹{negotiation_session.active_offer_card.amount_inr}"
                            )
                        except Exception as s5_err:
                            logger.error(f"Stage 5 initialization failure for {claim_id}: {s5_err}", exc_info=True)
                except Stage2Error as s2e:
                    # Expected domain guardrail escalation (ESC-03, ESC-05, ESC-06, ESC-07)
                    # The orchestrator has already recorded the escalation in PostgreSQL and emitted the SSE event.
                    logger.warning(
                        f"Stage 2 guardrail escalation for claim {claim_id}: "
                        f"code={s2e.escalation_code}, message={s2e.message}"
                    )
                except Stage2ModelCompatibilityError as s2_compat_err:
                    logger.error(
                        f"Stage 2 model compatibility failure for {claim_id}: {s2_compat_err.message}",
                        exc_info=True,
                    )
                    try:
                        await claim_repo.update_claim_stage(
                            claim_id=claim_id,
                            stage="STAGE_2_SEGMENTATION",
                            status="REJECTED_STAGE2_ERROR",
                            escalation_code=None,
                            failure_codes=["S2_MODEL_COMPATIBILITY_ERROR"],
                        )
                    except Exception as db_err:
                        logger.critical(
                            f"Failed to record stage 2 model compatibility error in DB for {claim_id}: {db_err}"
                        )
                    try:
                        await redis_manager.publish_event(
                            claim_id=claim_id,
                            event_name="STAGE_2_FAILED",
                            payload={
                                "claim_id": str(claim_id),
                                "status": "REJECTED_STAGE2_ERROR",
                                "failure_codes": ["S2_MODEL_COMPATIBILITY_ERROR"],
                            },
                        )
                    except Exception as redis_err:
                        logger.warning(
                            f"Failed to publish stage 2 compatibility failure event for {claim_id}: {redis_err}"
                        )
                except Exception as s2_err:
                    logger.error(f"Stage 2 unexpected execution failure for {claim_id}: {s2_err}", exc_info=True)
                    try:
                        await claim_repo.update_claim_stage(
                            claim_id=claim_id,
                            stage="STAGE_2_SEGMENTATION",
                            status="REJECTED_STAGE2_ERROR",
                            escalation_code=None,
                            failure_codes=["STAGE_2_INTERNAL_ERROR"],
                        )
                    except Exception as db_err:
                        logger.critical(f"Failed to record stage 2 crash in DB for {claim_id}: {db_err}")
                    try:
                        await redis_manager.publish_event(
                            claim_id=claim_id,
                            event_name="STAGE_2_FAILED",
                            payload={
                                "claim_id": str(claim_id),
                                "status": "REJECTED_STAGE2_ERROR",
                                "failure_codes": ["STAGE_2_INTERNAL_ERROR"],
                            },
                        )
                    except Exception as redis_err:
                        logger.warning(
                            f"Failed to publish stage 2 unexpected failure event for {claim_id}: {redis_err}"
                        )
    finally:
        # ponytail: prevent disk exhaustion by unlinking scratch file after pipeline completes
        if isinstance(scratch_path, (list, tuple)):
            for p in scratch_path:
                if p and Path(p).exists():
                    try:
                        Path(p).unlink(missing_ok=True)
                    except Exception as e:
                        logger.warning(f"Failed to unlink scratch photo {p}: {e}")
        elif scratch_path and Path(scratch_path).exists():
            try:
                Path(scratch_path).unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to unlink scratch file {scratch_path}: {e}")

router = APIRouter(prefix="/claims", tags=["claims"])

@router.post("/upload", response_model=FastFailResponseDTO, status_code=status.HTTP_202_ACCEPTED)
async def upload_claim_video(
    background_tasks: BackgroundTasks,
    policy_id: str = Form(...),
    capture_source: CaptureSource = Form(CaptureSource.FILE_UPLOAD),
    capture_modality: Optional[CaptureModality] = Form(None),
    is_demo_rehearsal: bool = Form(False),
    claim_description: Optional[str] = Form(None, max_length=1000),
    video_file: Optional[UploadFile] = File(None),
    photo_files: Optional[List[UploadFile]] = File(None),
    skip_stage_0: bool = Form(False),
    skip_stage_1: bool = Form(False),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Ingest point for claim media: video walkaround OR photo pack.
    Executes Stage 0 (Fast-Fail Gate).
    Returns HTTP 202 on pass, HTTP 200 with ESC-00 remediation on failure, HTTP 409 on lock conflict.
    """
    policy_repo = PolicyRepository(db)
    claim_repo = ClaimRepository(db)
    tier1_gate = PolicyAndDedupeGate(policy_repo, claim_repo)

    orchestrator = FastFailGateOrchestrator(
        ingest_service=scratch_ingest_service,
        redis_mgr=redis_manager,
        tier1_gate=tier1_gate,
        container_validator=container_forensics_validator,
        visual_validator=visual_quality_validator,
        remediation_mapper=remediation_mapper,
        claim_repo=claim_repo,
        s3_client=s3_client,
    )

    # Detect modality: photo pack vs video walkaround
    is_photo_pack = False
    valid_photos: List[UploadFile] = []
    if photo_files:
        valid_photos = [f for f in photo_files if f and getattr(f, "filename", None)]
        if valid_photos:
            is_photo_pack = True

    if not is_photo_pack and capture_modality == CaptureModality.PHOTO_PACK:
        is_photo_pack = True

    if is_photo_pack:
        try:
            response = await orchestrator.execute_photo_pack(
                claim_id=None,
                policy_id=policy_id,
                photo_paths=valid_photos or photo_files,
                is_demo_rehearsal=is_demo_rehearsal,
                background_tasks=background_tasks,
                downstream_task=run_stage1_pipeline_task,
                claim_description=claim_description,
                capture_source=capture_source,
                skip_stage_0=skip_stage_0,
                skip_stage_1=skip_stage_1,
            )
            if not response.passed:
                return JSONResponse(status_code=status.HTTP_200_OK, content=response.model_dump(mode="json"))
            return response
        except LockConflictException as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        except PayloadTooLargeException as e:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))
        except AutoSettleException as e:
            fail_code = FastFailFailureCode.CONTAINER_PARSE_FAILED
            rem = remediation_mapper.map_failures([fail_code])
            res = FastFailResponseDTO(
                passed=False,
                claim_id=uuid.uuid4(),
                escalation_code="ESC-00",
                failure_codes=[fail_code],
                remediation=rem,
            )
            return JSONResponse(status_code=status.HTTP_200_OK, content=res.model_dump(mode="json"))

    # Video Walkaround path
    if video_file is None or not getattr(video_file, "filename", None):
        # Neither valid video nor photo pack provided
        fail_code = FastFailFailureCode.CONTAINER_PARSE_FAILED
        rem = remediation_mapper.map_failures([fail_code])
        res = FastFailResponseDTO(
            passed=False,
            claim_id=uuid.uuid4(),
            escalation_code="ESC-00",
            failure_codes=[fail_code],
            remediation=rem,
        )
        return JSONResponse(status_code=status.HTTP_200_OK, content=res.model_dump(mode="json"))

    try:
        response = await orchestrator.execute(
            policy_id=policy_id,
            capture_source=capture_source,
            is_demo_rehearsal=is_demo_rehearsal,
            upload_file=video_file,
            background_tasks=background_tasks,
            downstream_task=run_stage1_pipeline_task,
            claim_description=claim_description,
            skip_stage_0=skip_stage_0,
            skip_stage_1=skip_stage_1,
        )

        if not response.passed:
            # Return HTTP 200 with remediation payload
            return JSONResponse(status_code=status.HTTP_200_OK, content=response.model_dump(mode="json"))

        return response

    except LockConflictException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PayloadTooLargeException as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))
    except AutoSettleException as e:
        # Gracefully handle corrupt or empty files as fast-fail ESC-00
        fail_code = FastFailFailureCode.CONTAINER_PARSE_FAILED
        rem = remediation_mapper.map_failures([fail_code])
        res = FastFailResponseDTO(
            passed=False,
            claim_id=uuid.uuid4(),
            escalation_code="ESC-00",
            failure_codes=[fail_code],
            remediation=rem,
        )
        return JSONResponse(status_code=status.HTTP_200_OK, content=res.model_dump(mode="json"))


@router.get("", status_code=status.HTTP_200_OK)
@router.get("/", status_code=status.HTTP_200_OK)
async def list_claims(limit: int = 50, db: AsyncSession = Depends(get_db_session)):
    """Lists recent claims with full forensic telemetry for desk hydration."""
    claim_repo = ClaimRepository(db)
    claims = await claim_repo.list_recent_claims(limit=limit)
    return [
        {
            "claim_id": str(claim.claim_id),
            "policy_id": claim.policy_id,
            "current_stage": claim.current_stage,
            "claim_status": claim.claim_status,
            "escalation_code": claim.escalation_code,
            "failure_codes": claim.failure_codes,
            "created_at": claim.created_at.isoformat() if claim.created_at else None,
            "telemetry": {
                "fast_fail": claim.fast_fail_telemetry,
                "vehicle_continuity": claim.vehicle_continuity_telemetry,
                "dual_mask": claim.dual_mask_telemetry,
                "vlm_inspection": claim.vlm_inspection_telemetry,
                "actuarial_estimate": claim.actuarial_estimate,
                "negotiation_session": claim.negotiation_session,
                "settlement_voucher": claim.settlement_voucher,
            },
        }
        for claim in claims
    ]


@router.get("/{claim_id}")
async def get_claim(claim_id: uuid.UUID, db: AsyncSession = Depends(get_db_session)):
    claim_repo = ClaimRepository(db)
    claim = await claim_repo.get_by_id(claim_id)
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")
    return {
        "claim_id": str(claim.claim_id),
        "policy_id": claim.policy_id,
        "current_stage": claim.current_stage,
        "claim_status": claim.claim_status,
        "escalation_code": claim.escalation_code,
        "failure_codes": claim.failure_codes,
        "telemetry": {
            "fast_fail": claim.fast_fail_telemetry,
            "vehicle_continuity": claim.vehicle_continuity_telemetry,
            "dual_mask": claim.dual_mask_telemetry,
            "vlm_inspection": claim.vlm_inspection_telemetry,
            "actuarial_estimate": claim.actuarial_estimate,
            "negotiation_session": claim.negotiation_session,
            "settlement_voucher": claim.settlement_voucher,
        },
    }


class AcceptOfferRequestDTO(BaseModel):
    offer_card: OfferCardDTO
    beneficiary_upi_id: Optional[str] = None


class RejectOfferRequestDTO(BaseModel):
    reason: Optional[str] = None
    preferred_garage: Optional[str] = None


@router.post("/{claim_id}/negotiate", response_model=NegotiationTurnDTO, status_code=status.HTTP_200_OK)
async def negotiate_claim(
    claim_id: uuid.UUID,
    payload: ClaimantMessageDTO,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Submits claimant counteroffer or conversational feedback.
    Returns the updated negotiation turn, chatbot explanation, and signed Offer Card.
    """
    from app.domain.negotiation_chatbot.orchestrator import Stage5NegotiationOrchestrator
    from app.domain.negotiation_chatbot.exceptions import (
        InvalidOfferTokenError,
        NegotiationRoundExhaustedError,
        NegotiationSessionTerminatedError,
        NegotiationError,
    )

    stage5_orch = Stage5NegotiationOrchestrator(db_session=db, redis_mgr=redis_manager)
    try:
        turn = await stage5_orch.process_claimant_turn(claim_id, payload)
        return turn
    except InvalidOfferTokenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except NegotiationRoundExhaustedError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except NegotiationSessionTerminatedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except NegotiationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{claim_id}/accept", response_model=SettlementVoucherDTO, status_code=status.HTTP_200_OK)
async def accept_settlement_offer(
    claim_id: uuid.UUID,
    payload: AcceptOfferRequestDTO,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Accepts cryptographic Offer Card, validates HMAC-SHA256 signature, commits
    damaged parts to unrepaired_claims_ledger, and issues official SettlementVoucher.
    """
    from app.domain.settlement_escalation.orchestrator import Stage6SettlementOrchestrator
    from app.domain.negotiation_chatbot.exceptions import InvalidOfferTokenError
    from app.domain.settlement_escalation.exceptions import SettlementError

    stage6_orch = Stage6SettlementOrchestrator(db_session=db, redis_mgr=redis_manager)
    try:
        voucher = await stage6_orch.finalize_settlement(
            claim_id=claim_id,
            accepted_offer=payload.offer_card,
            beneficiary_upi_id=payload.beneficiary_upi_id,
        )
        return voucher
    except InvalidOfferTokenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except SettlementError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{claim_id}/reject", status_code=status.HTTP_200_OK)
async def reject_cash_settlement(
    claim_id: uuid.UUID,
    payload: Optional[RejectOfferRequestDTO] = None,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Claimant rejects cash settlement to opt for Cashless Network Garage repair
    or Human Surveyor inspection.
    """
    from app.domain.settlement_escalation.orchestrator import Stage6SettlementOrchestrator

    stage6_orch = Stage6SettlementOrchestrator(db_session=db, redis_mgr=redis_manager)
    reason = payload.reason if payload and payload.reason else "Claimant selected authorized network cashless garage repair."
    dossier = await stage6_orch.escalate_claim(
        claim_id=claim_id,
        escalation_code="ESC-USER-REJECT",
        escalation_reason=reason,
    )
    return {
        "status": "ROUTED_CASHLESS_GARAGE",
        "claim_id": str(claim_id),
        "dossier_id": dossier.dossier_id,
        "message": "Claim transferred to Authorized Cashless Network Garage queue.",
    }


@router.get("/{claim_id}/negotiation", response_model=NegotiationSessionDTO, status_code=status.HTTP_200_OK)
async def get_negotiation_session(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Retrieves complete conversation history, rounds, and active offer card."""
    from app.domain.negotiation_chatbot.orchestrator import Stage5NegotiationOrchestrator

    stage5_orch = Stage5NegotiationOrchestrator(db_session=db, redis_mgr=redis_manager)
    session = await stage5_orch.get_session(claim_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Negotiation session not found for this claim.")
    return session


@router.get("/{claim_id}/voucher", response_model=SettlementVoucherDTO, status_code=status.HTTP_200_OK)
async def get_settlement_voucher(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Retrieves structured JSON settlement voucher for a settled claim."""
    from app.domain.settlement_escalation.orchestrator import Stage6SettlementOrchestrator

    stage6_orch = Stage6SettlementOrchestrator(db_session=db, redis_mgr=redis_manager)
    voucher = await stage6_orch.get_voucher(claim_id)
    if not voucher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settlement voucher not found for this claim.")
    return voucher


@router.get("/{claim_id}/voucher/pdf")
async def download_settlement_voucher_pdf(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Downloads official printable PDF Settlement Certificate."""
    from app.domain.settlement_escalation.orchestrator import Stage6SettlementOrchestrator
    from app.domain.settlement_escalation.pdf_service import reportlab_pdf_service

    stage6_orch = Stage6SettlementOrchestrator(db_session=db, redis_mgr=redis_manager)
    voucher = await stage6_orch.get_voucher(claim_id)
    if not voucher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Settlement voucher not found for this claim.")

    pdf_bytes = reportlab_pdf_service.generate_settlement_voucher_pdf(voucher)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=voucher_{claim_id}.pdf"},
    )


@router.get("/{claim_id}/dossier", response_model=HumanAdjusterDossierDTO, status_code=status.HTTP_200_OK)
async def get_adjuster_dossier(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Retrieves structured JSON Human Adjuster Review Dossier for an escalated claim."""
    from app.domain.settlement_escalation.orchestrator import Stage6SettlementOrchestrator

    stage6_orch = Stage6SettlementOrchestrator(db_session=db, redis_mgr=redis_manager)
    dossier = await stage6_orch.get_dossier(claim_id)
    if not dossier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Adjuster review dossier not found for this claim.")
    return dossier


@router.get("/{claim_id}/dossier/pdf")
async def download_adjuster_dossier_pdf(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Downloads official printable PDF Surveyor Claims Review Dossier."""
    from app.domain.settlement_escalation.orchestrator import Stage6SettlementOrchestrator
    from app.domain.settlement_escalation.pdf_service import reportlab_pdf_service

    stage6_orch = Stage6SettlementOrchestrator(db_session=db, redis_mgr=redis_manager)
    dossier = await stage6_orch.get_dossier(claim_id)
    if not dossier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Adjuster review dossier not found for this claim.")

    pdf_bytes = reportlab_pdf_service.generate_adjuster_dossier_pdf(dossier)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=dossier_{claim_id}.pdf"},
    )


@router.get("/{claim_id}/events")
async def stream_claim_events(claim_id: uuid.UUID):
    """
    Server-Sent Events (SSE) stream for real-time claim progress updates.
    """
    async def event_generator():
        client = await redis_manager.get_client()
        pubsub = client.pubsub()
        channel = f"claim:events:{claim_id}"
        await pubsub.subscribe(channel)

        try:
            # Yield initial connection heartbeat
            yield f"event: ping\ndata: {json.dumps({'status': 'connected', 'claim_id': str(claim_id)})}\n\n"

            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "message":
                    raw_data = message.get("data")
                    yield f"data: {raw_data}\n\n"
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
            raise

    return StreamingResponse(event_generator(), media_type="text/event-stream")
