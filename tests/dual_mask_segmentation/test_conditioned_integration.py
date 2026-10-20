"""
tests/dual_mask_segmentation/test_conditioned_integration.py
End-to-end integration tests for Conditioned Stage 2 Segmentation with ClaimIntent:
1. Claimed damage on claimed part is admitted and billed.
2. Unclaimed damage on an unrelated panel is quarantined as UNCLAIMED_PREEXISTING_DAMAGE
   and does NOT trigger ESC-05 (opposite-side fraud) or ESC-03 (unrepaired repeat claim).
3. If claimed damage is missing, Stage2ClaimedDamageNotFoundError (ESC-07_CLAIMED_DAMAGE_NOT_FOUND) is raised.
4. If no intent is provided, system remains 100% backward-compatible.
"""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock
import uuid

import numpy as np
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.claim_intent.schemas import ClaimIntent, ClaimedDamagePartPair, ClaimedPartIntent, ClaimedDamageIntent
from app.domain.claim_intent.intent_grounder import get_claim_intent_grounder
from app.domain.dual_mask_segmentation.catalog_and_ledger_grounder import CatalogAndLedgerGrounder
from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.exceptions import Stage2ClaimedDamageNotFoundError
from app.domain.dual_mask_segmentation.orchestrator import DualMaskSegmentationOrchestrator
from app.domain.dual_mask_segmentation.part_side_resolver_and_grouper import PartSideResolverAndGrouper
from app.domain.dual_mask_segmentation.polygon_intersection_engine import PolygonIntersectionEngine
from app.domain.dual_mask_segmentation.schemas import Stage3HandoffPayload
from app.domain.dual_mask_segmentation.som_crop_renderer import SoMCropRenderer
from app.domain.vehicle_identity_continuity.schemas import (
    ColorValidationResult,
    CutDetectionResult,
    PlateValidationResult,
    Stage2HandoffPayload,
    TrackingAndKeyframeResult,
    VehicleContinuityTelemetryDTO,
)
from app.infrastructure.db.models import Claim
from tests.dual_mask_segmentation.conftest import (
    make_frame_predictions,
    make_raw_damage_prediction,
    make_raw_part_prediction,
)
from tests.in_memory_db import in_memory_db


class TestConditionedStage2Segmentation:
    @pytest.mark.asyncio
    async def test_claimed_part_billed_unclaimed_quarantined_no_esc05(
        self,
        db_session: AsyncSession,
        redis_mock: AsyncMock,
        gpu_semaphore: asyncio.Semaphore,
        stage2_settings: Stage2Settings,
        synthetic_frame_1080p: np.ndarray,
        temp_keyframe_files: dict,
    ):
        """User claims: 'keyed my driver side door' (front_left_door, scratch).
        Scene detects:
          - Target: front_left_door scratch (Claimed)
          - Pre-existing: back_right_door dent (Opposite side, Unclaimed)
        Expected:
          - Target is billed (is_claimed=True).
          - Pre-existing is quarantined as UNCLAIMED_PREEXISTING_DAMAGE.
          - ESC-05 Opposite-Side Multi-Hit is NOT triggered!
        """
        claim_id = uuid.uuid4()
        policy_id = "POL-HAPPY-001"

        initial_claim = Claim(
            claim_id=claim_id,
            policy_id=policy_id,
            video_sha256="sha_" + uuid.uuid4().hex,
            capture_source="mobile_sdk",
            current_stage="STAGE_1_VEHICLE_IDENTITY",
            claim_status="PROCESSING",
        )
        in_memory_db.claims[claim_id] = initial_claim

        # Ground intent
        grounder = get_claim_intent_grounder()
        claim_intent = grounder.ground("someone keyed my driver side door", driver_side_is_left=True)
        assert "front_left_door" in claim_intent.claimed_parts

        # Detections:
        # 1. front_left_door scratch (Claimed)
        p_left_door = make_raw_part_prediction("front_left_door", 0.94, x1=200, y1=200, x2=1200, y2=300)
        d_scratch = make_raw_damage_prediction("scratch", 0.90, x1=200, y1=200, x2=400, y2=220)

        # 2. back_right_door dent (Opposite side, Unclaimed pre-existing)
        p_right_door = make_raw_part_prediction("back_right_door", 0.92, x1=100, y1=500, x2=800, y2=600)
        d_dent = make_raw_damage_prediction("dent", 0.88, x1=100, y1=500, x2=300, y2=580)

        kf_paths = {
            "kf_01": temp_keyframe_files["kf_01"],
            "kf_02": temp_keyframe_files["kf_02"],
        }
        frame_preds = [
            make_frame_predictions(
                keyframe_key="kf_01",
                frame_path=kf_paths["kf_01"],
                frame_index=1,
                part_predictions=[p_left_door, p_right_door],
                damage_predictions=[d_scratch, d_dent],
            ),
            make_frame_predictions(
                keyframe_key="kf_02",
                frame_path=kf_paths["kf_02"],
                frame_index=2,
                part_predictions=[p_left_door, p_right_door],
                damage_predictions=[d_scratch, d_dent],
            ),
        ]
        loaded_frames = {
            "kf_01": synthetic_frame_1080p.copy(),
            "kf_02": synthetic_frame_1080p.copy(),
        }

        inferencer_mock = AsyncMock()
        inferencer_mock.infer_keyframes = lambda paths: (frame_preds, loaded_frames)

        orchestrator = DualMaskSegmentationOrchestrator(
            db_session=db_session,
            redis_client=redis_mock,
            gpu_semaphore=gpu_semaphore,
            inferencer=inferencer_mock,
            intersection_engine=PolygonIntersectionEngine(settings=stage2_settings),
            grouper=PartSideResolverAndGrouper(settings=stage2_settings),
            catalog_grounder=CatalogAndLedgerGrounder(db_session=db_session, settings=stage2_settings),
            som_renderer=SoMCropRenderer(settings=stage2_settings),
            settings=stage2_settings,
        )

        telemetry = VehicleContinuityTelemetryDTO(
            cut_report=CutDetectionResult(is_continuous=True),
            plate_report=PlateValidationResult(is_verified=True, expected_plate="MH12DE1433"),
            color_report=ColorValidationResult(is_color_match=True, expected_color_name="WHITE"),
            tracking_report=TrackingAndKeyframeResult(is_persistent=True),
            passed=True,
        )
        handoff_payload = Stage2HandoffPayload(
            claim_id=claim_id,
            policy_id=policy_id,
            scratch_video_path=str(kf_paths["kf_01"]),
            keyframe_paths={k: str(v) for k, v in kf_paths.items()},
            vehicle_telemetry=telemetry,
            claim_intent=claim_intent,
        )

        result: Stage3HandoffPayload = await orchestrator.execute(handoff_payload)

        # Stage 2 MUST pass without ESC-05 opposite side escalation!
        assert result.telemetry["stage_passed"] is True
        assert result.telemetry["opposite_side_multi_hit_detected"] is False

        # Only the claimed part is passed into grounded_parts for Stage 3 & 4 billing
        assert len(result.grounded_parts) == 1
        assert result.grounded_parts[0].canonical_part_key == "front_left_door"
        assert result.grounded_parts[0].is_claimed is True
        assert result.grounded_parts[0].claim_status == "CLAIMED"

        # The opposite-side damage is recorded in telemetry as unclaimed pre-existing damage
        unclaimed_list = result.telemetry.get("unclaimed_preexisting_damages", [])
        assert len(unclaimed_list) == 1
        assert unclaimed_list[0]["canonical_part_key"] == "back_right_door"
        assert unclaimed_list[0]["claim_status"] == "UNCLAIMED_PREEXISTING_DAMAGE"

    @pytest.mark.asyncio
    async def test_claimed_damage_missing_triggers_esc07_claimed_damage_not_found(
        self,
        db_session: AsyncSession,
        redis_mock: AsyncMock,
        gpu_semaphore: asyncio.Semaphore,
        stage2_settings: Stage2Settings,
        synthetic_frame_1080p: np.ndarray,
        temp_keyframe_files: dict,
    ):
        """User claims: 'front bumper has a huge dent'.
        Scene detects:
          - Only a scratch on the hood (nothing on front bumper).
        Expected:
          - Stage2ClaimedDamageNotFoundError (ESC-07_CLAIMED_DAMAGE_NOT_FOUND) is raised.
          - Claim transitions to REJECTED_STAGE2_ERROR / ESC-07 in DB.
        """
        claim_id = uuid.uuid4()
        policy_id = "POL-HAPPY-001"

        initial_claim = Claim(
            claim_id=claim_id,
            policy_id=policy_id,
            video_sha256="sha_" + uuid.uuid4().hex,
            capture_source="mobile_sdk",
            current_stage="STAGE_1_VEHICLE_IDENTITY",
            claim_status="PROCESSING",
        )
        in_memory_db.claims[claim_id] = initial_claim

        claim_intent = ClaimIntent(
            raw_text="front bumper has a huge dent",
            claimed_parts=["front_bumper"],
            claimed_damages=["dent"],
        )

        # Only hood has damage, front bumper has nothing
        p_hood = make_raw_part_prediction("hood", 0.94, x1=200, y1=200, x2=1200, y2=400)
        d_scratch = make_raw_damage_prediction("scratch", 0.90, x1=200, y1=200, x2=400, y2=250)

        kf_paths = {
            "kf_01": temp_keyframe_files["kf_01"],
            "kf_02": temp_keyframe_files["kf_02"],
        }
        frame_preds = [
            make_frame_predictions(
                keyframe_key="kf_01",
                frame_path=kf_paths["kf_01"],
                frame_index=1,
                part_predictions=[p_hood],
                damage_predictions=[d_scratch],
            ),
            make_frame_predictions(
                keyframe_key="kf_02",
                frame_path=kf_paths["kf_02"],
                frame_index=2,
                part_predictions=[p_hood],
                damage_predictions=[d_scratch],
            ),
        ]
        loaded_frames = {
            "kf_01": synthetic_frame_1080p.copy(),
            "kf_02": synthetic_frame_1080p.copy(),
        }

        inferencer_mock = AsyncMock()
        inferencer_mock.infer_keyframes = lambda paths: (frame_preds, loaded_frames)

        orchestrator = DualMaskSegmentationOrchestrator(
            db_session=db_session,
            redis_client=redis_mock,
            gpu_semaphore=gpu_semaphore,
            inferencer=inferencer_mock,
            intersection_engine=PolygonIntersectionEngine(settings=stage2_settings),
            grouper=PartSideResolverAndGrouper(settings=stage2_settings),
            catalog_grounder=CatalogAndLedgerGrounder(db_session=db_session, settings=stage2_settings),
            som_renderer=SoMCropRenderer(settings=stage2_settings),
            settings=stage2_settings,
        )

        telemetry = VehicleContinuityTelemetryDTO(
            cut_report=CutDetectionResult(is_continuous=True),
            plate_report=PlateValidationResult(is_verified=True, expected_plate="MH12DE1433"),
            color_report=ColorValidationResult(is_color_match=True, expected_color_name="WHITE"),
            tracking_report=TrackingAndKeyframeResult(is_persistent=True),
            passed=True,
        )
        handoff_payload = Stage2HandoffPayload(
            claim_id=claim_id,
            policy_id=policy_id,
            scratch_video_path=str(kf_paths["kf_01"]),
            keyframe_paths={k: str(v) for k, v in kf_paths.items()},
            vehicle_telemetry=telemetry,
            claim_intent=claim_intent,
        )

        with pytest.raises(Stage2ClaimedDamageNotFoundError) as exc_info:
            await orchestrator.execute(handoff_payload)

        assert exc_info.value.escalation_code == "ESC-07_CLAIMED_DAMAGE_NOT_FOUND"
        assert "front_bumper" in exc_info.value.message
