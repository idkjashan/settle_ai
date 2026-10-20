import asyncio
import json
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, UploadFile, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.session import get_db_session
from app.infrastructure.db.repositories import PolicyRepository, ClaimRepository
from app.infrastructure.cache.redis_manager import redis_manager
from app.infrastructure.storage.scratch_ingest import scratch_ingest_service
from app.infrastructure.storage.s3_client import s3_client
from app.domain.fast_fail_gate.schemas import (
    CaptureSource,
    FastFailResponseDTO,
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


async def run_stage1_pipeline_task(
    claim_id: uuid.UUID, scratch_path, policy_id: str, is_demo_rehearsal: bool
):
    """Background task executing Stage 1 (Vehicle Identity & Continuity Grounding)."""
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
        try:
            telemetry = await stage1_orch.execute(
                claim_id=claim_id,
                scratch_video_path=scratch_path,
                policy_id=policy_id,
                is_demo_rehearsal=is_demo_rehearsal,
            )
            logger.info(f"Stage 1 background execution complete for {claim_id}: passed={telemetry.passed}")
        except Exception as e:
            logger.error(f"Stage 1 background execution failed for {claim_id}: {e}", exc_info=True)

router = APIRouter(prefix="/claims", tags=["claims"])

@router.post("/upload", response_model=FastFailResponseDTO, status_code=status.HTTP_202_ACCEPTED)
async def upload_claim_video(
    background_tasks: BackgroundTasks,
    policy_id: str = Form(...),
    capture_source: CaptureSource = Form(CaptureSource.FILE_UPLOAD),
    is_demo_rehearsal: bool = Form(False),
    video_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Ingest point for claim video walkaround.
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

    try:
        response = await orchestrator.execute(
            policy_id=policy_id,
            capture_source=capture_source,
            is_demo_rehearsal=is_demo_rehearsal,
            upload_file=video_file,
            background_tasks=background_tasks,
            downstream_task=run_stage1_pipeline_task,
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
        },
    }


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
