"""tests/dual_mask_segmentation/test_model_compatibility.py

Verifies strict taxonomy validation and safe failure contracts for Stage 2:
1. Missing model weights raise Stage2ModelCompatibilityError (no silent fallback).
2. Generic COCO weights (80 classes) are rejected for Carparts-Seg (23 classes) and CarDD-Seg (6 classes).
3. Renamed or spoofed checkpoints with incorrect class counts/names are rejected.
4. Models with mismatched class-ID-to-label mappings are rejected.
5. Models lacking a valid `names` dictionary are rejected.
6. Compatible models with exact taxonomies pass validation and map predictions accurately.
7. Detections with out-of-range class IDs are discarded rather than cross-wired.
8. Stage2ModelCompatibilityError is NOT a claim escalation error (does not inherit from Stage2Error).
"""
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
import pytest

from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.dual_model_inferencer import DualModelInferencer
from app.domain.dual_mask_segmentation.exceptions import (
    Stage2Error,
    Stage2ModelCompatibilityError,
)
from app.domain.dual_mask_segmentation.orchestrator import get_stage2_orchestrator
from app.domain.dual_mask_segmentation.taxonomy import (
    CARDD_CLASS_MAP,
    CARPARTS_CLASS_MAP,
    validate_model_taxonomy,
)
from tests.in_memory_db import FakeAsyncSession


# Helper to build mock YOLO models with specific `names` dictionaries
def make_mock_yolo_model(names_dict):
    mock_model = MagicMock()
    mock_model.names = names_dict
    return mock_model


class TestModelTaxonomyValidation:
    def test_missing_weights_raises_compatibility_error(self, tmp_path: Path):
        """Orchestrator factory must fail explicitly when weight files do not exist."""
        nonexistent_carparts = tmp_path / "nonexistent_carparts.pt"
        nonexistent_cardd = tmp_path / "nonexistent_cardd.pt"
        settings = Stage2Settings(
            carparts_model_path=str(nonexistent_carparts),
            cardd_model_path=str(nonexistent_cardd),
        )

        with pytest.raises(Stage2ModelCompatibilityError) as exc_info:
            get_stage2_orchestrator(
                db_session=FakeAsyncSession(),
                settings=settings,
            )

        err_msg = str(exc_info.value)
        assert "Carparts-Seg model weights not found" in err_msg
        assert "yolo11m-seg.pt" in err_msg  # Explains base weights cannot be substituted

    def test_generic_coco_model_rejected_for_carparts(self):
        """COCO 80-class model must be rejected for Carparts-Seg (expected 23 classes)."""
        coco_names = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle"}
        # Fill up to 80 COCO classes
        for i in range(4, 80):
            coco_names[i] = f"coco_object_{i}"
        coco_model = make_mock_yolo_model(coco_names)

        with pytest.raises(Stage2ModelCompatibilityError) as exc_info:
            validate_model_taxonomy(coco_model, CARPARTS_CLASS_MAP, model_role="Carparts-Seg")

        err = str(exc_info.value)
        assert "class count mismatch" in err
        assert "expected 23 classes, but model has 80 classes" in err

    def test_generic_coco_model_rejected_for_cardd(self):
        """COCO 80-class model must be rejected for CarDD-Seg (expected 6 classes)."""
        coco_names = {i: f"coco_class_{i}" for i in range(80)}
        coco_model = make_mock_yolo_model(coco_names)

        with pytest.raises(Stage2ModelCompatibilityError) as exc_info:
            validate_model_taxonomy(coco_model, CARDD_CLASS_MAP, model_role="CarDD-Seg")

        err = str(exc_info.value)
        assert "class count mismatch" in err
        assert "expected 6 classes, but model has 80 classes" in err

    def test_renamed_checkpoint_with_wrong_classes_rejected(self):
        """A checkpoint renamed to 'yolo11m-carparts-seg.pt' but containing COCO classes is rejected."""
        coco_names = {i: f"class_{i}" for i in range(80)}
        spoofed_model = make_mock_yolo_model(coco_names)

        with pytest.raises(Stage2ModelCompatibilityError):
            validate_model_taxonomy(spoofed_model, CARPARTS_CLASS_MAP, model_role="Carparts-Seg")

    def test_mismatched_class_names_rejected(self):
        """A model with 23 classes but incorrect labels (e.g. class 0 is 'person') is rejected."""
        wrong_names = dict(CARPARTS_CLASS_MAP)
        wrong_names[0] = "person"  # Was 'back_bumper'
        wrong_model = make_mock_yolo_model(wrong_names)

        with pytest.raises(Stage2ModelCompatibilityError) as exc_info:
            validate_model_taxonomy(wrong_model, CARPARTS_CLASS_MAP, model_role="Carparts-Seg")

        err = str(exc_info.value)
        assert "taxonomy mismatch at class ID 0" in err
        assert "expected 'back_bumper', got 'person'" in err

    def test_missing_names_attribute_rejected(self):
        """A model lacking a valid `names` attribute raises Stage2ModelCompatibilityError."""
        bad_model = MagicMock(spec=[])  # No attributes
        with pytest.raises(Stage2ModelCompatibilityError) as exc_info:
            validate_model_taxonomy(bad_model, CARPARTS_CLASS_MAP, model_role="Carparts-Seg")

        assert "lacks a valid 'names' attribute" in str(exc_info.value)

    def test_compatible_models_accepted(self):
        """Models with the exact expected Carparts and CarDD taxonomies pass validation."""
        valid_carparts = make_mock_yolo_model(CARPARTS_CLASS_MAP)
        valid_cardd = make_mock_yolo_model(CARDD_CLASS_MAP)

        # Should not raise any exception
        validate_model_taxonomy(valid_carparts, CARPARTS_CLASS_MAP, model_role="Carparts-Seg")
        validate_model_taxonomy(valid_cardd, CARDD_CLASS_MAP, model_role="CarDD-Seg")

        inferencer = DualModelInferencer(
            carparts_model=valid_carparts,
            cardd_model=valid_cardd,
            validate_taxonomy=True,
        )
        assert inferencer.carparts_model == valid_carparts
        assert inferencer.cardd_model == valid_cardd

    def test_prediction_mapping_with_compatible_model(self):
        """Verifies output parsing maps class IDs to canonical part and damage names."""
        valid_carparts = make_mock_yolo_model(CARPARTS_CLASS_MAP)
        valid_cardd = make_mock_yolo_model(CARDD_CLASS_MAP)
        inferencer = DualModelInferencer(valid_carparts, valid_cardd, validate_taxonomy=True)

        # Mock Ultralytics result
        mock_res = MagicMock()
        mock_res.boxes.xyxy.cpu().numpy.return_value = np.array([[10, 20, 200, 300]], dtype=float)
        mock_res.boxes.conf.cpu().numpy.return_value = np.array([0.92], dtype=float)
        mock_res.boxes.cls.cpu().numpy.return_value = np.array([11])  # front_left_door
        # 4 normalized points for polygon
        mock_res.masks.xyn = [np.array([[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]])]

        parsed = inferencer._parse_ultralytics_result(
            mock_res, CARPARTS_CLASS_MAP, width_px=1000, height_px=500, filter_ignored=True
        )
        assert len(parsed) == 1
        assert parsed[0].class_id == 11
        assert parsed[0].class_name == "front_left_door"
        assert parsed[0].confidence == 0.92
        assert parsed[0].bbox_xyxy == (10, 20, 200, 300)

    def test_out_of_range_class_id_discarded(self):
        """Class IDs not in the canonical class map are safely discarded."""
        valid_carparts = make_mock_yolo_model(CARPARTS_CLASS_MAP)
        valid_cardd = make_mock_yolo_model(CARDD_CLASS_MAP)
        inferencer = DualModelInferencer(valid_carparts, valid_cardd, validate_taxonomy=True)

        mock_res = MagicMock()
        mock_res.boxes.xyxy.cpu().numpy.return_value = np.array([[10, 20, 200, 300]], dtype=float)
        mock_res.boxes.conf.cpu().numpy.return_value = np.array([0.90], dtype=float)
        mock_res.boxes.cls.cpu().numpy.return_value = np.array([99])  # Out of range class ID
        mock_res.masks.xyn = [np.array([[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]])]

        parsed = inferencer._parse_ultralytics_result(
            mock_res, CARPARTS_CLASS_MAP, width_px=1000, height_px=500, filter_ignored=True
        )
        assert len(parsed) == 0

    def test_model_compatibility_error_is_not_claim_escalation(self):
        """Stage2ModelCompatibilityError must NOT inherit from Stage2Error.
        
        Ensures model infrastructure failures never falsely masquerade as insurance claim
        business escalations (ESC-03..ESC-07) or mark claims as safe.
        """
        err = Stage2ModelCompatibilityError("Missing weights")
        assert not isinstance(err, Stage2Error), "Must not inherit from Stage2Error"
        assert err.code == "STAGE_2_MODEL_COMPATIBILITY_ERROR"

    def test_non_integer_dict_keys_raises_compatibility_error(self):
        """Dictionary with non-integer keys raises Stage2ModelCompatibilityError with an informative message."""
        bad_model = make_mock_yolo_model({"invalid_str_key": "front_bumper"})
        with pytest.raises(Stage2ModelCompatibilityError) as exc_info:
            validate_model_taxonomy(bad_model, CARPARTS_CLASS_MAP, model_role="Carparts-Seg")
        err = str(exc_info.value)
        assert "non-integer keys" in err

        # Also test None key
        bad_model_none = make_mock_yolo_model({None: "front_bumper"})
        with pytest.raises(Stage2ModelCompatibilityError) as exc_info2:
            validate_model_taxonomy(bad_model_none, CARPARTS_CLASS_MAP, model_role="Carparts-Seg")
        assert "non-integer keys" in str(exc_info2.value)

    def test_valid_list_and_tuple_names_accepted(self):
        """List and tuple of class names are accepted and correctly map zero-indexed classes."""
        carparts_list = [CARPARTS_CLASS_MAP[i] for i in range(len(CARPARTS_CLASS_MAP))]
        model_list = make_mock_yolo_model(carparts_list)
        validate_model_taxonomy(model_list, CARPARTS_CLASS_MAP, model_role="Carparts-Seg")

        cardd_tuple = tuple(CARDD_CLASS_MAP[i] for i in range(len(CARDD_CLASS_MAP)))
        model_tuple = make_mock_yolo_model(cardd_tuple)
        validate_model_taxonomy(model_tuple, CARDD_CLASS_MAP, model_role="CarDD-Seg")

    def test_non_contiguous_class_ids_rejected(self):
        """Models with 23 classes but non-contiguous keys (1-23 missing 0) are rejected."""
        non_contiguous = {i + 1: CARPARTS_CLASS_MAP[i] for i in range(len(CARPARTS_CLASS_MAP))}
        model = make_mock_yolo_model(non_contiguous)
        with pytest.raises(Stage2ModelCompatibilityError) as exc_info:
            validate_model_taxonomy(model, CARPARTS_CLASS_MAP, model_role="Carparts-Seg")
        err = str(exc_info.value)
        assert "missing expected class ID 0" in err


class TestStage2PipelineErrorHandling:
    """Verifies that Stage 2 model compatibility failures and unexpected runtime errors

    in the API background task cleanly transition the claim state in PostgreSQL,
    emit SSE failure events, and never leave claims stuck in PROCESSING or use ESC-07.
    """

    @pytest.fixture
    def valid_stage1_telemetry(self):
        from app.domain.vehicle_identity_continuity.schemas import (
            ColorValidationResult,
            CutDetectionResult,
            PlateValidationResult,
            TrackingAndKeyframeResult,
            VehicleContinuityTelemetryDTO,
        )
        return VehicleContinuityTelemetryDTO(
            cut_report=CutDetectionResult(is_continuous=True),
            plate_report=PlateValidationResult(is_verified=True, expected_plate="MH12DE1433"),
            color_report=ColorValidationResult(is_color_match=True, expected_color_name="WHITE"),
            tracking_report=TrackingAndKeyframeResult(
                is_persistent=True,
                saved_keyframes={"kf_01": "dummy_kf.jpg"},
            ),
            passed=True,
        )

    @pytest.mark.asyncio
    async def test_background_task_missing_weights_transitions_claim_state(self, valid_stage1_telemetry):
        """When fine-tuned weights are missing, the background task transitions the claim to

        REJECTED_STAGE2_ERROR with failure_codes=['S2_MODEL_COMPATIBILITY_ERROR'], escalation_code=None,
        and emits a STAGE_2_FAILED SSE event. The claim does not hang in PROCESSING.
        """
        import uuid
        from unittest.mock import patch
        from app.api.v1.endpoints.claims_router import run_stage1_pipeline_task
        from app.domain.vehicle_identity_continuity.orchestrator import VehicleIdentityContinuityOrchestrator
        from app.infrastructure.db.models import Claim
        from app.infrastructure.db.repositories import ClaimRepository
        from tests.in_memory_db import in_memory_db

        claim_id = uuid.uuid4()
        claim_repo = ClaimRepository(FakeAsyncSession())
        active_claim = Claim(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            video_sha256="dummy_sha_" + uuid.uuid4().hex,
            capture_source="FILE_UPLOAD",
            is_demo_rehearsal=False,
            current_stage="STAGE_1_IDENTITY",
            claim_status="PROCESSING",
        )
        await claim_repo.create_claim(active_claim)

        with patch.object(VehicleIdentityContinuityOrchestrator, "execute", return_value=valid_stage1_telemetry):
            await run_stage1_pipeline_task(
                claim_id=claim_id,
                scratch_path=Path("/tmp/dummy_scratch.mp4"),
                policy_id="POL-HAPPY-001",
                is_demo_rehearsal=False,
            )

        fresh = in_memory_db.claims[claim_id]
        assert fresh.claim_status == "REJECTED_STAGE2_ERROR", f"Expected REJECTED_STAGE2_ERROR, got {fresh.claim_status}"
        assert fresh.current_stage == "STAGE_2_SEGMENTATION"
        assert fresh.escalation_code is None, f"Expected None, got {fresh.escalation_code}"
        assert "S2_MODEL_COMPATIBILITY_ERROR" in fresh.failure_codes

        # Verify SSE event
        matching_events = [e for e in in_memory_db.events if e.get("claim_id") == claim_id and e.get("event") == "STAGE_2_FAILED"]
        assert len(matching_events) == 1
        assert matching_events[0]["data"]["status"] == "REJECTED_STAGE2_ERROR"
        assert matching_events[0]["data"]["failure_codes"] == ["S2_MODEL_COMPATIBILITY_ERROR"]

    @pytest.mark.asyncio
    async def test_background_task_unexpected_runtime_error_no_esc07(self, valid_stage1_telemetry):
        """Unexpected runtime errors during Stage 2 execution must NOT be tagged with ESC-07.

        escalation_code must be None, and failure_codes must include STAGE_2_INTERNAL_ERROR.
        """
        import uuid
        from unittest.mock import AsyncMock, patch
        from app.api.v1.endpoints.claims_router import run_stage1_pipeline_task
        from app.domain.vehicle_identity_continuity.orchestrator import VehicleIdentityContinuityOrchestrator
        import app.domain.dual_mask_segmentation.orchestrator as s2_orch_mod
        from app.infrastructure.db.models import Claim
        from app.infrastructure.db.repositories import ClaimRepository
        from tests.in_memory_db import in_memory_db

        claim_id = uuid.uuid4()
        claim_repo = ClaimRepository(FakeAsyncSession())
        active_claim = Claim(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            video_sha256="dummy_sha_" + uuid.uuid4().hex,
            capture_source="FILE_UPLOAD",
            is_demo_rehearsal=False,
            current_stage="STAGE_1_IDENTITY",
            claim_status="PROCESSING",
        )
        await claim_repo.create_claim(active_claim)

        mock_orch = MagicMock()
        mock_orch.execute = AsyncMock(side_effect=RuntimeError("Simulated CUDA Out Of Memory"))

        with patch.object(VehicleIdentityContinuityOrchestrator, "execute", return_value=valid_stage1_telemetry):
            with patch.object(s2_orch_mod, "get_stage2_orchestrator", return_value=mock_orch):
                await run_stage1_pipeline_task(
                    claim_id=claim_id,
                    scratch_path=Path("/tmp/dummy_scratch.mp4"),
                    policy_id="POL-HAPPY-001",
                    is_demo_rehearsal=False,
                )

        fresh = in_memory_db.claims[claim_id]
        assert fresh.claim_status == "REJECTED_STAGE2_ERROR"
        assert fresh.current_stage == "STAGE_2_SEGMENTATION"
        assert fresh.escalation_code is None, f"Internal crash must NOT be mapped to ESC-07! Got {fresh.escalation_code}"
        assert "STAGE_2_INTERNAL_ERROR" in fresh.failure_codes

    @pytest.mark.asyncio
    async def test_background_task_stage2_guardrail_escalation_preserved(self, valid_stage1_telemetry):
        """When a legitimate Stage2Error guardrail escalation occurs (e.g. ESC-07 low confidence),

        it is logged as a warning and preserved; it is not overwritten by REJECTED_STAGE2_ERROR.
        """
        import uuid
        from unittest.mock import AsyncMock, patch
        from app.api.v1.endpoints.claims_router import run_stage1_pipeline_task
        from app.domain.dual_mask_segmentation.exceptions import Stage2LowConfidenceOrNoDamageError
        from app.domain.vehicle_identity_continuity.orchestrator import VehicleIdentityContinuityOrchestrator
        import app.domain.dual_mask_segmentation.orchestrator as s2_orch_mod
        from app.infrastructure.db.models import Claim
        from app.infrastructure.db.repositories import ClaimRepository
        from tests.in_memory_db import in_memory_db

        claim_id = uuid.uuid4()
        claim_repo = ClaimRepository(FakeAsyncSession())
        active_claim = Claim(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            video_sha256="dummy_sha_" + uuid.uuid4().hex,
            capture_source="FILE_UPLOAD",
            is_demo_rehearsal=False,
            current_stage="STAGE_1_IDENTITY",
            claim_status="PROCESSING",
        )
        await claim_repo.create_claim(active_claim)

        mock_orch = MagicMock()
        mock_orch.execute = AsyncMock(
            side_effect=Stage2LowConfidenceOrNoDamageError("Zero damage found", ["NO_DAMAGE_DETECTED"])
        )

        with patch.object(VehicleIdentityContinuityOrchestrator, "execute", return_value=valid_stage1_telemetry):
            with patch.object(s2_orch_mod, "get_stage2_orchestrator", return_value=mock_orch):
                await run_stage1_pipeline_task(
                    claim_id=claim_id,
                    scratch_path=Path("/tmp/dummy_scratch.mp4"),
                    policy_id="POL-HAPPY-001",
                    is_demo_rehearsal=False,
                )

        fresh = in_memory_db.claims[claim_id]
        assert fresh.claim_status != "REJECTED_STAGE2_ERROR", "Guardrail escalation must not be overwritten by REJECTED_STAGE2_ERROR"

    @pytest.mark.asyncio
    async def test_no_stage3_handoff_on_compatibility_failure(self, valid_stage1_telemetry):
        """Confirms that when Stage 2 fails, no downstream Stage 3 payload or transition is triggered."""
        import uuid
        from unittest.mock import patch
        from app.api.v1.endpoints.claims_router import run_stage1_pipeline_task
        from app.domain.vehicle_identity_continuity.orchestrator import VehicleIdentityContinuityOrchestrator
        from app.infrastructure.db.models import Claim
        from app.infrastructure.db.repositories import ClaimRepository
        from tests.in_memory_db import in_memory_db

        claim_id = uuid.uuid4()
        claim_repo = ClaimRepository(FakeAsyncSession())
        active_claim = Claim(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            video_sha256="dummy_sha_" + uuid.uuid4().hex,
            capture_source="FILE_UPLOAD",
            is_demo_rehearsal=False,
            current_stage="STAGE_1_IDENTITY",
            claim_status="PROCESSING",
        )
        await claim_repo.create_claim(active_claim)

        with patch.object(VehicleIdentityContinuityOrchestrator, "execute", return_value=valid_stage1_telemetry):
            await run_stage1_pipeline_task(
                claim_id=claim_id,
                scratch_path=Path("/tmp/dummy_scratch.mp4"),
                policy_id="POL-HAPPY-001",
                is_demo_rehearsal=False,
            )

        fresh = in_memory_db.claims[claim_id]
        assert fresh.current_stage != "STAGE_3_VLM_INSPECTION", "Stage 3 handoff must not occur"
        assert fresh.claim_status != "PASSED", "Claim must not be marked passed"

