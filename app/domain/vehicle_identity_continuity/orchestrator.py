import asyncio
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List
import cv2
import numpy as np
import torch
from app.core.config import settings
from app.domain.vehicle_identity_continuity.config import stage1_settings
from app.domain.vehicle_identity_continuity.schemas import (
    PolicyGroundingContext,
    VehicleContinuityTelemetryDTO,
    Stage1HandoffPayload,
    CutDetectionResult,
    PlateValidationResult,
    ColorValidationResult,
    TrackingAndKeyframeResult,
)
from app.domain.vehicle_identity_continuity.cut_detector import cut_detector, CutDetector
from app.domain.vehicle_identity_continuity.plate_ocr_validator import plate_ocr_validator, PlateOCRValidator
from app.domain.vehicle_identity_continuity.color_grounding_validator import color_grounding_validator, ColorGroundingValidator
from app.domain.vehicle_identity_continuity.object_tracker import object_tracker, ObjectTracker
from app.infrastructure.db.repositories import PolicyRepository, ClaimRepository
from app.infrastructure.cache.redis_manager import RedisManager, redis_manager
from app.core.logging import logger

class VehicleIdentityContinuityOrchestrator:
    def __init__(
        self,
        policy_repo: PolicyRepository,
        claim_repo: ClaimRepository,
        redis_mgr: Optional[RedisManager] = None,
        cut_det: Optional[CutDetector] = None,
        plate_val: Optional[PlateOCRValidator] = None,
        color_val: Optional[ColorGroundingValidator] = None,
        tracker: Optional[ObjectTracker] = None,
    ):
        self.policy_repo = policy_repo
        self.claim_repo = claim_repo
        self.redis_mgr = redis_mgr or redis_manager
        self.cut_detector = cut_det or cut_detector
        self.plate_validator = plate_val or plate_ocr_validator
        self.color_validator = color_val or color_grounding_validator
        self.tracker = tracker or object_tracker
        self.settings = stage1_settings
        self._gpu_lock = asyncio.Semaphore(1)

    async def execute(
        self,
        claim_id: uuid.UUID,
        scratch_video_path: Path,
        policy_id: str,
        is_demo_rehearsal: bool = False,
    ) -> VehicleContinuityTelemetryDTO:
        try:
            return await self._execute_internal(
                claim_id=claim_id,
                scratch_video_path=scratch_video_path,
                policy_id=policy_id,
                is_demo_rehearsal=is_demo_rehearsal,
            )
        finally:
            # ponytail: release CUDA cache and purge ephemeral scratch files after Stage 1
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            if scratch_video_path and Path(scratch_video_path).is_relative_to(Path(settings.SCRATCH_DIR)):
                try:
                    Path(scratch_video_path).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Could not unlink scratch video {scratch_video_path}: {e}")

    async def _execute_internal(
        self,
        claim_id: uuid.UUID,
        scratch_video_path: Path,
        policy_id: str,
        is_demo_rehearsal: bool = False,
    ) -> VehicleContinuityTelemetryDTO:
        t0 = time.perf_counter()

        # Step 0: Policy Grounding Fetch
        policy = await self.policy_repo.get_by_id(policy_id)
        if not policy:
            logger.error(f"Stage 1 failed: Policy {policy_id} not found.")
            telemetry = VehicleContinuityTelemetryDTO(
                cut_report=CutDetectionResult(is_continuous=False, failure_code="ESC-01"),
                plate_report=PlateValidationResult(is_verified=False, expected_plate="", failure_code="ESC-01"),
                color_report=ColorValidationResult(is_color_match=False, expected_color_name="", failure_code="ESC-01"),
                tracking_report=TrackingAndKeyframeResult(is_persistent=False, failure_code="ESC-01"),
                total_execution_ms=(time.perf_counter() - t0) * 1000.0,
                passed=False,
                escalation_code="ESC-01",
            )
            await self._update_failed_claim(claim_id, "REJECTED_STAGE1_IDENTITY", "ESC-01", telemetry)
            return telemetry

        grounding_context = PolicyGroundingContext(
            policy_id=policy.policy_id,
            registration_number=policy.registration_number,
            make=policy.make,
            model=policy.model,
            registered_color=policy.registered_color,
            registered_color_hsv=policy.registered_color_hsv,
        )

        # Step 1: Gate 1 — Fast CPU Continuity & Splice Firewall (< 100ms)
        cut_report: CutDetectionResult = await asyncio.to_thread(
            self.cut_detector.evaluate, scratch_video_path
        )
        if not cut_report.is_continuous:
            total_ms = (time.perf_counter() - t0) * 1000.0
            fail_code = cut_report.failure_code or "S1_CUT_HISTOGRAM_DROP"
            telemetry = VehicleContinuityTelemetryDTO(
                cut_report=cut_report,
                plate_report=PlateValidationResult(is_verified=False, expected_plate=grounding_context.registration_number),
                color_report=ColorValidationResult(is_color_match=False, expected_color_name=grounding_context.registered_color),
                tracking_report=TrackingAndKeyframeResult(is_persistent=False),
                total_execution_ms=total_ms,
                passed=False,
                escalation_code="ESC-02",
            )
            await self._update_failed_claim(
                claim_id, "REJECTED_STAGE1_CONTINUITY", "ESC-02", telemetry, failure_codes=[fail_code]
            )
            return telemetry

        # Step 2: Gate 2A — Initial Window Vehicle & ANPR Grounding (< 250ms)
        async with self._gpu_lock:
            plate_report: PlateValidationResult = await asyncio.to_thread(
                self.plate_validator.validate_initial_window,
                scratch_video_path,
                grounding_context.registration_number,
                self.settings.INITIAL_WINDOW_SECONDS,
            )

        if not plate_report.is_verified and not plate_report.deferred_to_late_track:
            # Definite wrong plate detected or plate mismatch!
            total_ms = (time.perf_counter() - t0) * 1000.0
            fail_code = plate_report.failure_code or "S1_PLATE_MISMATCH"
            telemetry = VehicleContinuityTelemetryDTO(
                cut_report=cut_report,
                plate_report=plate_report,
                color_report=ColorValidationResult(is_color_match=False, expected_color_name=grounding_context.registered_color),
                tracking_report=TrackingAndKeyframeResult(is_persistent=False),
                total_execution_ms=total_ms,
                passed=False,
                escalation_code="ESC-01",
            )
            await self._update_failed_claim(
                claim_id, "REJECTED_STAGE1_IDENTITY", "ESC-01", telemetry, failure_codes=[fail_code]
            )
            return telemetry

        # Step 3: Gate 2C — Dominant Body Paint HSV Grounding (< 20ms)
        color_report = ColorValidationResult(
            is_color_match=True, expected_color_name=grounding_context.registered_color
        )
        color_verified = False
        if plate_report.anchor_vehicle_bbox is not None:
            anchor_frame = self._read_single_frame(scratch_video_path, plate_report.anchor_frame_idx)
            if anchor_frame is not None:
                color_report = self.color_validator.validate_paint_color(
                    anchor_frame, plate_report.anchor_vehicle_bbox, grounding_context
                )
                color_verified = True
                if not color_report.is_color_match:
                    total_ms = (time.perf_counter() - t0) * 1000.0
                    fail_code = color_report.failure_code or "S1_COLOR_MISMATCH"
                    telemetry = VehicleContinuityTelemetryDTO(
                        cut_report=cut_report,
                        plate_report=plate_report,
                        color_report=color_report,
                        tracking_report=TrackingAndKeyframeResult(is_persistent=False),
                        total_execution_ms=total_ms,
                        passed=False,
                        escalation_code="ESC-01",
                    )
                    await self._update_failed_claim(
                        claim_id, "REJECTED_STAGE1_IDENTITY", "ESC-01", telemetry, failure_codes=[fail_code]
                    )
                    return telemetry

        # Step 4: Gate 3 — Reset-Safe Strided ByteTrack & Keyframes (< 500ms)
        async with self._gpu_lock:
            track_report: TrackingAndKeyframeResult = await asyncio.to_thread(
                self.tracker.track_and_extract_keyframes,
                scratch_video_path,
                str(claim_id),
                grounding_context,
                plate_report.deferred_to_late_track,
                plate_report,
            )

        if not track_report.is_persistent:
            total_ms = (time.perf_counter() - t0) * 1000.0
            fail_code = track_report.failure_code or "S1_TRACK_LOST_EXCEEDED"
            telemetry = VehicleContinuityTelemetryDTO(
                cut_report=cut_report,
                plate_report=plate_report,
                color_report=color_report,
                tracking_report=track_report,
                total_execution_ms=total_ms,
                passed=False,
                escalation_code="ESC-02",
            )
            await self._update_failed_claim(
                claim_id, "REJECTED_STAGE1_CONTINUITY", "ESC-02", telemetry, failure_codes=[fail_code]
            )
            return telemetry

        # Check late plate verification if was deferred
        if plate_report.deferred_to_late_track and not plate_report.is_verified:
            if track_report.late_plate_verified:
                plate_report.is_verified = True
                plate_report.failure_code = None
            else:
                # If still not verified after whole track
                logger.warning(f"Plate remained unverified after full track for claim {claim_id}.")
                total_ms = (time.perf_counter() - t0) * 1000.0
                fail_code = "S1_PLATE_NOT_FOUND_OR_UNREADABLE"
                telemetry = VehicleContinuityTelemetryDTO(
                    cut_report=cut_report,
                    plate_report=plate_report,
                    color_report=color_report,
                    tracking_report=track_report,
                    total_execution_ms=total_ms,
                    passed=False,
                    escalation_code="ESC-01",
                )
                await self._update_failed_claim(
                    claim_id, "REJECTED_STAGE1_IDENTITY", "ESC-01", telemetry, failure_codes=[fail_code]
                )
                return telemetry

        # ponytail: Late-track color grounding enforcement on reverse walkarounds
        if not color_verified and plate_report.is_verified and plate_report.anchor_vehicle_bbox is not None:
            late_anchor_frame = self._read_single_frame(scratch_video_path, plate_report.anchor_frame_idx)
            if late_anchor_frame is not None:
                color_report = self.color_validator.validate_paint_color(
                    late_anchor_frame, plate_report.anchor_vehicle_bbox, grounding_context
                )
                if not color_report.is_color_match:
                    total_ms = (time.perf_counter() - t0) * 1000.0
                    fail_code = color_report.failure_code or "S1_COLOR_MISMATCH"
                    telemetry = VehicleContinuityTelemetryDTO(
                        cut_report=cut_report,
                        plate_report=plate_report,
                        color_report=color_report,
                        tracking_report=track_report,
                        total_execution_ms=total_ms,
                        passed=False,
                        escalation_code="ESC-01",
                    )
                    await self._update_failed_claim(
                        claim_id, "REJECTED_STAGE1_IDENTITY", "ESC-01", telemetry, failure_codes=[fail_code]
                    )
                    return telemetry

        # All Gates in Stage 1 Passed!
        total_ms = (time.perf_counter() - t0) * 1000.0
        telemetry = VehicleContinuityTelemetryDTO(
            cut_report=cut_report,
            plate_report=plate_report,
            color_report=color_report,
            tracking_report=track_report,
            total_execution_ms=total_ms,
            passed=True,
            escalation_code=None,
        )

        # Commit to PostgreSQL
        await self.claim_repo.update_claim_stage(
            claim_id=claim_id,
            stage="STAGE_2_SEGMENTATION",
            status="PROCESSING",
            telemetry_update=telemetry.model_dump(),
            telemetry_column="vehicle_continuity_telemetry",
        )

        # Emit Redis SSE event
        await self.redis_mgr.publish_event(
            claim_id=claim_id,
            event_name="STAGE_1_PASSED",
            payload={
                "claim_id": str(claim_id),
                "status": "PROCESSING",
                "stage": "STAGE_2_SEGMENTATION",
                "keyframes": track_report.saved_keyframes,
                "duration_ms": total_ms,
            },
        )

        logger.info(f"Stage 1 fully PASSED for claim {claim_id} in {total_ms:.2f}ms.")
        return telemetry

    async def execute_photo_pack(
        self,
        claim_id: uuid.UUID,
        photo_paths: List[Path],
        policy_id: str,
        is_demo_rehearsal: bool = False,
    ) -> VehicleContinuityTelemetryDTO:
        """
        Executes Stage 1 Vehicle Identity Grounding for still Photo Pack:
        1. ANPR plate OCR verification on plate candidate photo.
        2. Body paint color HSV grounding on context photo.
        3. Direct mapping of photos to canonical keyframes (front_bumper, damage_closeup_primary, side_body_panel).
        4. State transition to STAGE_2_SEGMENTATION.
        """
        try:
            return await self._execute_photo_pack_internal(
                claim_id=claim_id,
                photo_paths=photo_paths,
                policy_id=policy_id,
                is_demo_rehearsal=is_demo_rehearsal,
            )
        finally:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    async def _execute_photo_pack_internal(
        self,
        claim_id: uuid.UUID,
        photo_paths: List[Path],
        policy_id: str,
        is_demo_rehearsal: bool = False,
    ) -> VehicleContinuityTelemetryDTO:
        t0 = time.perf_counter()

        # Step 0: Policy Grounding Fetch
        policy = await self.policy_repo.get_by_id(policy_id)
        if not policy:
            logger.error(f"Stage 1 Photo Pack failed: Policy {policy_id} not found.")
            telemetry = VehicleContinuityTelemetryDTO(
                cut_report=CutDetectionResult(is_continuous=False, failure_code="ESC-01"),
                plate_report=PlateValidationResult(is_verified=False, expected_plate="", failure_code="ESC-01"),
                color_report=ColorValidationResult(is_color_match=False, expected_color_name="", failure_code="ESC-01"),
                tracking_report=TrackingAndKeyframeResult(is_persistent=False, failure_code="ESC-01"),
                total_execution_ms=(time.perf_counter() - t0) * 1000.0,
                passed=False,
                escalation_code="ESC-01",
            )
            await self._update_failed_claim(claim_id, "REJECTED_STAGE1_IDENTITY", "ESC-01", telemetry)
            return telemetry

        grounding_context = PolicyGroundingContext(
            policy_id=policy.policy_id,
            registration_number=policy.registration_number,
            make=policy.make,
            model=policy.model,
            registered_color=policy.registered_color,
            registered_color_hsv=policy.registered_color_hsv,
        )

        resolved_photos = [Path(p) for p in photo_paths]

        # Step 1: Read photos
        loaded_images: Dict[Path, Optional[np.ndarray]] = {}
        for p in resolved_photos:
            img = cv2.imread(str(p))
            loaded_images[p] = img

        # Step 2: Identify candidate photos (plate candidate, context candidate, damage closeup candidate)
        plate_photo: Optional[Path] = None
        context_photo: Optional[Path] = None
        damage_photo: Optional[Path] = None

        for p in resolved_photos:
            name_lower = p.name.lower()
            if "plate" in name_lower or "front_bumper" in name_lower:
                if plate_photo is None:
                    plate_photo = p
            elif "context" in name_lower or "side" in name_lower or "overview" in name_lower:
                if context_photo is None:
                    context_photo = p
            elif "closeup" in name_lower or "damage" in name_lower or "macro" in name_lower:
                if damage_photo is None:
                    damage_photo = p

        # Step 3: Run ANPR on plate candidate photo or scan photos
        plate_report: Optional[PlateValidationResult] = None
        best_plate_photo: Optional[Path] = None

        candidate_plate_photos = [plate_photo] if plate_photo else resolved_photos
        for p in candidate_plate_photos:
            if p is None:
                continue
            img = loaded_images.get(p)
            if img is None:
                continue
            rep = self.plate_validator.validate_plate_in_image(img, grounding_context.registration_number)
            if plate_report is None or rep.is_verified or rep.homoglyph_edit_cost < plate_report.homoglyph_edit_cost:
                plate_report = rep
                best_plate_photo = p
            if rep.is_verified:
                break

        # Fallback to test remaining photos if not yet verified
        if plate_report is None or not plate_report.is_verified:
            for p in resolved_photos:
                if p == best_plate_photo:
                    continue
                img = loaded_images.get(p)
                if img is None:
                    continue
                rep = self.plate_validator.validate_plate_in_image(img, grounding_context.registration_number)
                if plate_report is None or rep.homoglyph_edit_cost < plate_report.homoglyph_edit_cost:
                    plate_report = rep
                    best_plate_photo = p
                if rep.is_verified:
                    plate_report = rep
                    best_plate_photo = p
                    break

        if best_plate_photo:
            plate_photo = best_plate_photo

        if plate_report is None:
            plate_report = PlateValidationResult(
                is_verified=False,
                expected_plate=grounding_context.registration_number,
                failure_code="S1_PLATE_NOT_FOUND_OR_UNREADABLE",
            )

        if not plate_report.is_verified:
            total_ms = (time.perf_counter() - t0) * 1000.0
            fail_code = plate_report.failure_code or "S1_PLATE_MISMATCH"
            telemetry = VehicleContinuityTelemetryDTO(
                cut_report=CutDetectionResult(is_continuous=True, evaluated_frames=len(resolved_photos)),
                plate_report=plate_report,
                color_report=ColorValidationResult(is_color_match=False, expected_color_name=grounding_context.registered_color),
                tracking_report=TrackingAndKeyframeResult(is_persistent=False),
                total_execution_ms=total_ms,
                passed=False,
                escalation_code="ESC-01",
            )
            await self._update_failed_claim(
                claim_id, "REJECTED_STAGE1_IDENTITY", "ESC-01", telemetry, failure_codes=[fail_code]
            )
            return telemetry

        # Step 4: Body color HSV grounding on context photo
        if context_photo is None or context_photo == plate_photo:
            non_plate_photos = [p for p in resolved_photos if p != plate_photo]
            context_photo = non_plate_photos[0] if non_plate_photos else plate_photo

        context_img = loaded_images.get(context_photo)
        if context_img is not None:
            h_c, w_c = context_img.shape[:2]
            vehicle_bbox = plate_report.anchor_vehicle_bbox or (0, 0, w_c, h_c)
            color_report = self.color_validator.validate_paint_color(
                context_img, vehicle_bbox, grounding_context
            )
        else:
            color_report = ColorValidationResult(
                is_color_match=False,
                expected_color_name=grounding_context.registered_color,
                failure_code="S1_COLOR_MISMATCH",
            )

        if not color_report.is_color_match:
            total_ms = (time.perf_counter() - t0) * 1000.0
            fail_code = color_report.failure_code or "S1_COLOR_MISMATCH"
            telemetry = VehicleContinuityTelemetryDTO(
                cut_report=CutDetectionResult(is_continuous=True, evaluated_frames=len(resolved_photos)),
                plate_report=plate_report,
                color_report=color_report,
                tracking_report=TrackingAndKeyframeResult(is_persistent=False),
                total_execution_ms=total_ms,
                passed=False,
                escalation_code="ESC-01",
            )
            await self._update_failed_claim(
                claim_id, "REJECTED_STAGE1_IDENTITY", "ESC-01", telemetry, failure_codes=[fail_code]
            )
            return telemetry

        # Step 5: Map photos directly to canonical keyframes:
        # front_bumper.jpg, damage_closeup_primary.jpg, side_body_panel.jpg
        if damage_photo is None or damage_photo in (plate_photo, context_photo):
            remaining = [p for p in resolved_photos if p not in (plate_photo, context_photo)]
            damage_photo = remaining[0] if remaining else (context_photo or plate_photo)

        saved_keyframes: Dict[str, str] = {
            "front_bumper": str(plate_photo),
            "damage_closeup_primary": str(damage_photo),
            "side_body_panel": str(context_photo),
        }
        additional_keys = ["rear_bumper", "hood", "trunk_lid", "front_left_door", "front_right_door"]
        used_photos = {plate_photo, context_photo, damage_photo}
        extra_idx = 0
        for p in resolved_photos:
            if p not in used_photos:
                key = additional_keys[extra_idx] if extra_idx < len(additional_keys) else f"extra_panel_{extra_idx}"
                saved_keyframes[key] = str(p)
                extra_idx += 1

        curated_keyframes = [str(p) for p in resolved_photos]

        track_report = TrackingAndKeyframeResult(
            is_persistent=True,
            frames_tracked=len(resolved_photos),
            saved_keyframes=saved_keyframes,
            curated_keyframes=curated_keyframes,
            late_plate_verified=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

        total_ms = (time.perf_counter() - t0) * 1000.0
        telemetry = VehicleContinuityTelemetryDTO(
            cut_report=CutDetectionResult(is_continuous=True, evaluated_frames=len(resolved_photos)),
            plate_report=plate_report,
            color_report=color_report,
            tracking_report=track_report,
            total_execution_ms=total_ms,
            passed=True,
            escalation_code=None,
        )

        # Commit to PostgreSQL
        await self.claim_repo.update_claim_stage(
            claim_id=claim_id,
            stage="STAGE_2_SEGMENTATION",
            status="PROCESSING",
            telemetry_update=telemetry.model_dump(),
            telemetry_column="vehicle_continuity_telemetry",
        )

        # Emit Redis SSE event
        await self.redis_mgr.publish_event(
            claim_id=claim_id,
            event_name="STAGE_1_PASSED",
            payload={
                "claim_id": str(claim_id),
                "status": "PROCESSING",
                "stage": "STAGE_2_SEGMENTATION",
                "keyframes": track_report.saved_keyframes,
                "duration_ms": total_ms,
                "modality": "PHOTO_PACK",
            },
        )

        logger.info(f"Stage 1 Photo Pack fully PASSED for claim {claim_id} in {total_ms:.2f}ms.")
        return telemetry

    async def _update_failed_claim(
        self,
        claim_id: uuid.UUID,
        claim_status: str,
        escalation_code: str,
        telemetry: VehicleContinuityTelemetryDTO,
        failure_codes: Optional[list[str]] = None,
    ) -> None:
        codes = failure_codes or [escalation_code]
        await self.claim_repo.update_claim_stage(
            claim_id=claim_id,
            stage="STAGE_1_IDENTITY",
            status=claim_status,
            escalation_code=escalation_code,
            failure_codes=codes,
            telemetry_update=telemetry.model_dump(),
            telemetry_column="vehicle_continuity_telemetry",
        )
        await self.redis_mgr.publish_event(
            claim_id=claim_id,
            event_name="STAGE_1_FAILED",
            payload={
                "claim_id": str(claim_id),
                "status": claim_status,
                "escalation_code": escalation_code,
                "failure_codes": codes,
                "duration_ms": telemetry.total_execution_ms,
            },
        )

    def _read_single_frame(self, video_path: Path, frame_idx: int) -> Optional[np.ndarray]:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            return frame if ret else None
        finally:
            cap.release()

vehicle_identity_continuity_orchestrator = None
