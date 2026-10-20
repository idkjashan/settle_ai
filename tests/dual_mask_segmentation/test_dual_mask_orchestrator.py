"""
tests/dual_mask_segmentation/test_dual_mask_orchestrator.py
Verifies End-to-End Orchestrator Pipeline:
- T2-01: End-to-end happy path for Hyundai Creta front_left_door with dent (IoP=0.084 / 8.4%),
         verifying Stage3HandoffPayload construction, PostgreSQL database update to
         STAGE_3_VLM_INSPECTION, and Redis SSE event publication.
"""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock
import uuid

import numpy as np
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dual_mask_segmentation.catalog_and_ledger_grounder import (
    CatalogAndLedgerGrounder,
)
from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.orchestrator import DualMaskSegmentationOrchestrator
from app.domain.dual_mask_segmentation.part_side_resolver_and_grouper import (
    PartSideResolverAndGrouper,
)
from app.domain.dual_mask_segmentation.polygon_intersection_engine import (
    PolygonIntersectionEngine,
)
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


class TestDualMaskOrchestrator:
    @pytest.mark.asyncio
    async def test_t2_01_end_to_end_happy_path_creta_door(
        self,
        db_session: AsyncSession,
        redis_mock: AsyncMock,
        gpu_semaphore: asyncio.Semaphore,
        stage2_settings: Stage2Settings,
        synthetic_frame_1080p: np.ndarray,
        temp_keyframe_files: dict,
    ):
        """T2-01: End-to-end pipeline execution for Hyundai Creta:
        - Carparts-Seg detects unclipped 'front_left_door' (100,000 px^2)
        - CarDD detects 'dent' (8,400 px^2) -> IoP = 0.084 (8.4%)
        - Persisted across multiple frames
        - Grounded against Hyundai Creta OEM parts catalogue in PostgreSQL
        - Zero unrepaired prior claims
        - Non-occluding SoM crops and SVG paths rendered
        - Claim updated in DB: STAGE_3_VLM_INSPECTION, claim_status=PROCESSING
        - Redis SSE event emitted on claim:events:<claim_id>
        - Stage3HandoffPayload returned with all grounded parts
        """
        claim_id = uuid.uuid4()
        policy_id = "POL-HAPPY-001"

        # 1. Seed initial claim in DB
        initial_claim = Claim(
            claim_id=claim_id,
            policy_id=policy_id,
            video_sha256="deadbeef1234567890abcdefdeadbeef1234567890abcdefdeadbeef12345678",
            capture_source="mobile_sdk",
            current_stage="STAGE_1_VEHICLE_IDENTITY",
            claim_status="PROCESSING",
        )
        in_memory_db.claims[claim_id] = initial_claim

        # 2. Setup synthetic predictions for 2 consecutive keyframes
        # Door: [200, 200, 1200, 300] -> width 1000, height 100 = 100,000 px^2
        # Dent: [200, 200, 305, 280] -> width 105, height 80 = 8,400 px^2 -> IoP = 0.084 (8.4%)
        p_door = make_raw_part_prediction(
            class_name="front_left_door",
            confidence=0.94,
            x1=200,
            y1=200,
            x2=1200,
            y2=300,
        )
        d_dent = make_raw_damage_prediction(
            class_name="dent",
            confidence=0.89,
            x1=200,
            y1=200,
            x2=305,
            y2=280,
        )

        kf_paths = {
            "kf_01": temp_keyframe_files["kf_01"],
            "kf_02": temp_keyframe_files["kf_02"],
        }
        frame_preds = [
            make_frame_predictions(
                keyframe_key="kf_01",
                frame_path=kf_paths["kf_01"],
                frame_index=1,
                part_predictions=[p_door],
                damage_predictions=[d_dent],
            ),
            make_frame_predictions(
                keyframe_key="kf_02",
                frame_path=kf_paths["kf_02"],
                frame_index=2,
                part_predictions=[p_door],
                damage_predictions=[d_dent],
            ),
        ]
        loaded_frames = {
            "kf_01": synthetic_frame_1080p.copy(),
            "kf_02": synthetic_frame_1080p.copy(),
        }

        # 3. Create mock inferencer returning the predictions and loaded frames
        inferencer_mock = AsyncMock()
        inferencer_mock.infer_keyframes = lambda paths: (frame_preds, loaded_frames)

        # 4. Instantiate real domain pipeline components
        intersection_engine = PolygonIntersectionEngine(settings=stage2_settings)
        grouper = PartSideResolverAndGrouper(settings=stage2_settings)
        catalog_grounder = CatalogAndLedgerGrounder(db_session=db_session, settings=stage2_settings)
        som_renderer = SoMCropRenderer(settings=stage2_settings)

        orchestrator = DualMaskSegmentationOrchestrator(
            db_session=db_session,
            redis_client=redis_mock,
            gpu_semaphore=gpu_semaphore,
            inferencer=inferencer_mock,
            intersection_engine=intersection_engine,
            grouper=grouper,
            catalog_grounder=catalog_grounder,
            som_renderer=som_renderer,
            settings=stage2_settings,
        )

        # 5. Build Stage 1 handoff payload
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
        )

        # 6. Execute Orchestrator
        result: Stage3HandoffPayload = await orchestrator.execute(handoff_payload)

        # 7. Invariant Assertions on Returned Stage3HandoffPayload
        assert isinstance(result, Stage3HandoffPayload)
        assert result.claim_id == claim_id
        assert result.policy_id == policy_id
        assert result.registration_number == "MH12DE1433"
        assert result.make == "Hyundai"
        assert result.model == "Creta"
        assert len(result.grounded_parts) == 1

        part = result.grounded_parts[0]
        assert part.canonical_part_key == "front_left_door"
        assert part.primary_damage_class == "dent"
        assert part.display_part_name == "Front Left Door Panel"
        assert part.oem_part_number == "76003-M0000"
        assert part.final_iop_ratio == pytest.approx(0.084, abs=1e-3)
        assert part.iop_percentage == pytest.approx(8.40, abs=0.1)
        assert part.persistence_frame_count == 2
        assert part.som_raw_crop_path.exists()
        assert part.som_annotated_crop_path.exists()

        # Telemetry assertion
        assert result.telemetry["stage_passed"] is True
        assert result.telemetry["schema_version"] == "2.0.0"
        assert result.telemetry["opposite_side_multi_hit_detected"] is False
        assert result.telemetry["safety_critical_damage_detected"] is False
        assert result.telemetry["unrepaired_repeat_claim_detected"] is False

        # 8. Assert DB Commit
        updated_claim = in_memory_db.claims[claim_id]
        assert updated_claim.current_stage == "STAGE_3_VLM_INSPECTION"
        assert updated_claim.claim_status == "PROCESSING"
        assert updated_claim.dual_mask_telemetry is not None
        assert updated_claim.dual_mask_telemetry["stage_passed"] is True

        # 9. Assert Redis SSE Event Publication
        redis_mock.publish.assert_called_once()
        channel, raw_msg = redis_mock.publish.call_args[0]
        assert channel == f"claim:events:{claim_id}"
        event_dict = json.loads(raw_msg)
        assert event_dict["event"] == "STAGE_2_PASSED"
        assert event_dict["claim_id"] == str(claim_id)
        assert len(event_dict["damaged_parts"]) == 1
        assert event_dict["damaged_parts"][0]["canonical_part_key"] == "front_left_door"
        assert event_dict["damaged_parts"][0]["iop_percentage"] == pytest.approx(8.40, abs=0.1)
