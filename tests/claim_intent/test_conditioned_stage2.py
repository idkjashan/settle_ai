"""
tests/claim_intent/test_conditioned_stage2.py
Verification suite for Conditioned Stage 2 Detection:
- PolygonIntersectionEngine tags is_claimed=True/False and claim_status.
- PartSideResolverAndGrouper sorts user-claimed candidates first.
- DualMaskSegmentationOrchestrator routes unclaimed damages to telemetry without billing.
- DualMaskSegmentationOrchestrator raises Stage2ClaimedDamageNotFoundError (ESC-07_CLAIMED_DAMAGE_NOT_FOUND)
  when claimed damage is missing from camera detections.
- API endpoint POST /api/v1/claims/upload accepts optional claim_description.
"""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import numpy as np
import pytest
from shapely.geometry import Polygon

from app.domain.claim_intent.schemas import ClaimIntent
from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.exceptions import Stage2ClaimedDamageNotFoundError
from app.domain.dual_mask_segmentation.part_side_resolver_and_grouper import PartSideResolverAndGrouper
from app.domain.dual_mask_segmentation.polygon_intersection_engine import PolygonIntersectionEngine
from app.domain.dual_mask_segmentation.orchestrator import DualMaskSegmentationOrchestrator
from app.domain.dual_mask_segmentation.schemas import (
    FrameDualPredictions,
    GroupedPartCandidate,
    PartDamageIntersection,
    RawMaskPrediction,
    Stage3HandoffPayload,
)
from app.domain.vehicle_identity_continuity.schemas import Stage2HandoffPayload


# -----------------------------------------------------------------------------
# Helper factories for synthetic spatial geometries
# -----------------------------------------------------------------------------

def _make_box_coords(xmin: int, ymin: int, xmax: int, ymax: int) -> np.ndarray:
    return np.array([[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]], dtype=np.int32)


def _make_dummy_intersection(
    part_key: str, damage_class: str, is_claimed: bool = True
) -> PartDamageIntersection:
    poly = Polygon([(100, 100), (400, 100), (400, 400), (100, 400)])
    dmg_poly = Polygon([(150, 150), (250, 150), (250, 250), (150, 250)])
    return PartDamageIntersection(
        keyframe_key="kf_01",
        frame_index=1,
        width_px=1280,
        height_px=720,
        laplacian_sharpness=120.0,
        raw_part_class=part_key,
        resolved_part_key=part_key,
        part_confidence=0.92,
        part_bbox_xyxy=(100, 100, 400, 400),
        is_complete_panel=True,
        border_contact_ratio=0.0,
        part_area_px=90000.0,
        union_damage_intersection_area_px=10000.0,
        raw_iop_ratio=0.1111,
        damage_classes=[damage_class],
        primary_damage_class=damage_class,
        max_damage_confidence=0.88,
        part_polygon=poly,
        union_damage_polygon=dmg_poly,
        is_claimed=is_claimed,
        claim_status="CLAIMED" if is_claimed else "UNCLAIMED_PREEXISTING_DAMAGE",
    )


class TestConditionedStage2:
    """Test suite for Conditioned Stage 2 Detection pipeline."""

    # -------------------------------------------------------------------------
    # 1. Polygon Intersection Engine Intent Tagging
    # -------------------------------------------------------------------------

    def test_polygon_intersection_engine_intent_tagging(self):
        """Verifies that polygon engine tags matching hits as CLAIMED and non-matching as UNCLAIMED_PREEXISTING_DAMAGE."""
        engine = PolygonIntersectionEngine(settings=Stage2Settings())

        door_poly = _make_box_coords(100, 100, 400, 400)
        door_scratch = _make_box_coords(150, 150, 250, 250)
        bumper_poly = _make_box_coords(500, 100, 800, 400)
        bumper_dent = _make_box_coords(550, 150, 650, 250)

        frame = FrameDualPredictions(
            keyframe_key="kf_01",
            frame_path=Path("/dummy/kf_01.jpg"),
            frame_index=1,
            width_px=1280,
            height_px=720,
            laplacian_sharpness=150.0,
            part_predictions=[
                RawMaskPrediction(class_id=1, class_name="front_left_door", confidence=0.95, bbox_xyxy=(100, 100, 400, 400), polygon_xy_px=door_poly),
                RawMaskPrediction(class_id=2, class_name="back_bumper", confidence=0.92, bbox_xyxy=(500, 100, 800, 400), polygon_xy_px=bumper_poly),
            ],
            damage_predictions=[
                RawMaskPrediction(class_id=10, class_name="scratch", confidence=0.88, bbox_xyxy=(150, 150, 250, 250), polygon_xy_px=door_scratch),
                RawMaskPrediction(class_id=11, class_name="dent", confidence=0.85, bbox_xyxy=(550, 150, 650, 250), polygon_xy_px=bumper_dent),
            ],
        )

        claim_intent = ClaimIntent(
            raw_text="someone keyed my driver side door",
            claimed_parts=["front_left_door"],
            claimed_damages=["scratch"],
            is_empty=False,
        )

        intersections, _, _ = engine.compute_intersections([frame], claim_intent=claim_intent)
        assert len(intersections) == 2

        door_hit = next(h for h in intersections if h.raw_part_class == "front_left_door")
        assert door_hit.is_claimed is True
        assert door_hit.claim_status == "CLAIMED"

        bumper_hit = next(h for h in intersections if h.raw_part_class == "back_bumper")
        assert bumper_hit.is_claimed is False
        assert bumper_hit.claim_status == "UNCLAIMED_PREEXISTING_DAMAGE"

    def test_polygon_intersection_engine_empty_intent_defaults_to_claimed(self):
        """Verifies that when no intent is provided, all detected damages are tagged CLAIMED."""
        engine = PolygonIntersectionEngine(settings=Stage2Settings())
        door_poly = _make_box_coords(100, 100, 400, 400)
        door_scratch = _make_box_coords(150, 150, 250, 250)

        frame = FrameDualPredictions(
            keyframe_key="kf_01",
            frame_path=Path("/dummy/kf_01.jpg"),
            frame_index=1,
            width_px=1280,
            height_px=720,
            laplacian_sharpness=150.0,
            part_predictions=[
                RawMaskPrediction(class_id=1, class_name="front_left_door", confidence=0.95, bbox_xyxy=(100, 100, 400, 400), polygon_xy_px=door_poly)
            ],
            damage_predictions=[
                RawMaskPrediction(class_id=10, class_name="scratch", confidence=0.88, bbox_xyxy=(150, 150, 250, 250), polygon_xy_px=door_scratch)
            ],
        )

        intersections, _, _ = engine.compute_intersections([frame], claim_intent=None)
        assert len(intersections) == 1
        assert intersections[0].is_claimed is True
        assert intersections[0].claim_status == "CLAIMED"

    # -------------------------------------------------------------------------
    # 2. Grouper Claimed-First Prioritization
    # -------------------------------------------------------------------------

    def test_grouper_prioritizes_claimed_candidates_first(self):
        """Verifies grouper sorts user-claimed candidates ahead of unclaimed ones regardless of IOP."""
        grouper = PartSideResolverAndGrouper(settings=Stage2Settings())

        hit_door = _make_dummy_intersection("front_left_door", "scratch", is_claimed=True)
        hit_door.raw_iop_ratio = 0.05

        hit_bumper = _make_dummy_intersection("back_bumper", "dent", is_claimed=False)
        hit_bumper.raw_iop_ratio = 0.40

        claim_intent = ClaimIntent(
            raw_text="keyed driver door",
            claimed_parts=["front_left_door"],
            claimed_damages=["scratch"],
            is_empty=False,
        )

        candidates = grouper.resolve_and_group(
            intersections=[hit_bumper, hit_door],
            predictions=[],
            unclipped_part_areas={},
            claim_intent=claim_intent,
        )

        assert len(candidates) == 2
        assert candidates[0].canonical_part_key == "front_left_door"
        assert candidates[0].is_claimed is True
        assert candidates[0].claim_status == "CLAIMED"

        assert candidates[1].canonical_part_key == "back_bumper"
        assert candidates[1].is_claimed is False
        assert candidates[1].claim_status == "UNCLAIMED_PREEXISTING_DAMAGE"

    # -------------------------------------------------------------------------
    # 3. Orchestrator Claimed Damage Not Found (ESC-07_CLAIMED_DAMAGE_NOT_FOUND)
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_orchestrator_raises_esc07_when_claimed_damage_not_found(self):
        """User claims front_left_door scratch, but camera detections only have back_bumper dent.
        Must raise Stage2ClaimedDamageNotFoundError (ESC-07_CLAIMED_DAMAGE_NOT_FOUND).
        """
        mock_inferencer = MagicMock()
        mock_inferencer.infer_keyframes.return_value = ([], {})

        mock_geo = MagicMock()
        mock_geo.compute_intersections.return_value = ([], [], {})

        unclaimed_candidate = GroupedPartCandidate(
            canonical_part_key="back_bumper",
            raw_detected_part_classes=["back_bumper"],
            side_resolution_method="DIRECT_EXPLICIT_CLASS",
            detected_damage_classes=["dent"],
            primary_damage_class="dent",
            final_iop_ratio=0.15,
            iop_estimation_method="UNCLIPPED_COMPLETE_PANEL",
            zoom_clipped_frames_filtered=0,
            persistence_frame_count=2,
            part_confidence=0.9,
            damage_confidence=0.85,
            area_measurement_intersection=_make_dummy_intersection("back_bumper", "dent", is_claimed=False),
            vlm_closeup_intersection=_make_dummy_intersection("back_bumper", "dent", is_claimed=False),
            is_claimed=False,
            claim_status="UNCLAIMED_PREEXISTING_DAMAGE",
        )
        mock_grouper = MagicMock()
        mock_grouper.resolve_and_group.return_value = [unclaimed_candidate]

        mock_catalog = MagicMock()
        mock_som = MagicMock()
        mock_db = AsyncMock()
        mock_redis = AsyncMock()
        mock_semaphore = AsyncMock()

        orchestrator = DualMaskSegmentationOrchestrator(
            db_session=mock_db,
            redis_client=mock_redis,
            gpu_semaphore=mock_semaphore,
            inferencer=mock_inferencer,
            intersection_engine=mock_geo,
            grouper=mock_grouper,
            catalog_grounder=mock_catalog,
            som_renderer=mock_som,
        )

        claim_id = uuid.uuid4()
        claim_intent = ClaimIntent(
            raw_text="someone keyed my driver side door",
            claimed_parts=["front_left_door"],
            claimed_damages=["scratch"],
            is_empty=False,
        )
        payload = Stage2HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            scratch_video_path="/dummy/video.mp4",
            keyframe_paths={"kf_01": "/dummy/kf_01.jpg"},
            claim_intent=claim_intent,
        )

        with pytest.raises(Stage2ClaimedDamageNotFoundError) as exc_info:
            await orchestrator.execute(payload)

        err = exc_info.value
        assert err.escalation_code == "ESC-07_CLAIMED_DAMAGE_NOT_FOUND"
        assert "ESC-07_CLAIMED_DAMAGE_NOT_FOUND" in err.failure_codes
        assert "not detected on camera" in err.message

    # -------------------------------------------------------------------------
    # 4. Orchestrator Filters Unclaimed Damage from Billing
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_orchestrator_routes_unclaimed_damage_to_telemetry_without_billing(self):
        """User claims front_left_door. Camera detects BOTH front_left_door AND back_bumper.
        front_left_door proceeds to catalog billing, back_bumper is routed to telemetry only.
        """
        mock_inferencer = MagicMock()
        mock_inferencer.infer_keyframes.return_value = ([], {})
        mock_geo = MagicMock()
        mock_geo.compute_intersections.return_value = ([], [], {})

        claimed_cand = GroupedPartCandidate(
            canonical_part_key="front_left_door",
            raw_detected_part_classes=["front_left_door"],
            side_resolution_method="DIRECT_EXPLICIT_CLASS",
            detected_damage_classes=["scratch"],
            primary_damage_class="scratch",
            final_iop_ratio=0.08,
            iop_estimation_method="UNCLIPPED_COMPLETE_PANEL",
            zoom_clipped_frames_filtered=0,
            persistence_frame_count=2,
            part_confidence=0.94,
            damage_confidence=0.91,
            area_measurement_intersection=_make_dummy_intersection("front_left_door", "scratch", is_claimed=True),
            vlm_closeup_intersection=_make_dummy_intersection("front_left_door", "scratch", is_claimed=True),
            is_claimed=True,
            claim_status="CLAIMED",
        )
        unclaimed_cand = GroupedPartCandidate(
            canonical_part_key="back_bumper",
            raw_detected_part_classes=["back_bumper"],
            side_resolution_method="DIRECT_EXPLICIT_CLASS",
            detected_damage_classes=["dent"],
            primary_damage_class="dent",
            final_iop_ratio=0.22,
            iop_estimation_method="UNCLIPPED_COMPLETE_PANEL",
            zoom_clipped_frames_filtered=0,
            persistence_frame_count=2,
            part_confidence=0.92,
            damage_confidence=0.88,
            area_measurement_intersection=_make_dummy_intersection("back_bumper", "dent", is_claimed=False),
            vlm_closeup_intersection=_make_dummy_intersection("back_bumper", "dent", is_claimed=False),
            is_claimed=False,
            claim_status="UNCLAIMED_PREEXISTING_DAMAGE",
        )

        mock_grouper = MagicMock()
        mock_grouper.resolve_and_group.return_value = [claimed_cand, unclaimed_cand]

        mock_catalog = MagicMock()
        grounding_result = MagicMock()
        grounding_result.verified_pairs = [MagicMock()]
        grounding_result.registration_number = "DL01AB1234"
        grounding_result.make = "Hyundai"
        grounding_result.model = "Creta"
        mock_catalog.ground_and_check_guardrails = AsyncMock(return_value=grounding_result)

        mock_som = MagicMock()
        mock_som.render_artifacts.return_value = []

        mock_db = AsyncMock()
        mock_redis = AsyncMock()
        mock_semaphore = AsyncMock()

        orchestrator = DualMaskSegmentationOrchestrator(
            db_session=mock_db,
            redis_client=mock_redis,
            gpu_semaphore=mock_semaphore,
            inferencer=mock_inferencer,
            intersection_engine=mock_geo,
            grouper=mock_grouper,
            catalog_grounder=mock_catalog,
            som_renderer=mock_som,
        )

        claim_id = uuid.uuid4()
        claim_intent = ClaimIntent(
            raw_text="keyed driver door",
            claimed_parts=["front_left_door"],
            claimed_damages=["scratch"],
            is_empty=False,
        )
        payload = Stage2HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            scratch_video_path="/dummy/video.mp4",
            keyframe_paths={"kf_01": "/dummy/kf_01.jpg"},
            claim_intent=claim_intent,
        )

        handoff = await orchestrator.execute(payload)

        # 1. Catalog grounder must ONLY have been called with front_left_door (NOT back_bumper)
        mock_catalog.ground_and_check_guardrails.assert_awaited_once()
        passed_candidates = mock_catalog.ground_and_check_guardrails.call_args[0][1]
        assert len(passed_candidates) == 1
        assert passed_candidates[0].canonical_part_key == "front_left_door"

        # 2. Handoff must contain unclaimed back_bumper in unclaimed_preexisting_parts
        assert len(handoff.unclaimed_preexisting_parts) == 1
        assert handoff.unclaimed_preexisting_parts[0].canonical_part_key == "back_bumper"

        # 3. Telemetry must document unclaimed damage
        assert "unclaimed_preexisting_damages" in handoff.telemetry
        unclaimed_telemetry = handoff.telemetry["unclaimed_preexisting_damages"]
        assert len(unclaimed_telemetry) == 1
        assert unclaimed_telemetry[0]["canonical_part_key"] == "back_bumper"
        assert unclaimed_telemetry[0]["claim_status"] == "UNCLAIMED_PREEXISTING_DAMAGE"

    # -------------------------------------------------------------------------
    # 5. API Upload Integration
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_api_upload_accepts_claim_description(self, async_client, dummy_video_file: Path):
        """Verifies POST /api/v1/claims/upload accepts optional claim_description form field."""
        from app.domain.fast_fail_gate.schemas import ContainerGateReport, VisualGateReport

        captured_intent_text = None

        async def mock_downstream_task(*args, **kwargs):
            nonlocal captured_intent_text
            if len(args) >= 5:
                captured_intent_text = args[4]
            elif "claim_description" in kwargs:
                captured_intent_text = kwargs["claim_description"]

        mock_container = ContainerGateReport(
            passed=True,
            failure_codes=[],
            format_name="mov,mp4",
            width=1280,
            height=720,
            duration_sec=15.0,
            effective_fps=30.0,
            codec_name="h264",
        )
        mock_visual = VisualGateReport(
            passed=True,
            failure_codes=[],
            mean_luminance_aggregate=120.0,
            mean_sharpness_aggregate=100.0,
        )

        with patch("app.api.v1.endpoints.claims_router.run_stage1_pipeline_task", mock_downstream_task), \
             patch("app.domain.fast_fail_gate.container_forensics.ContainerForensicsValidator.validate", return_value=mock_container), \
             patch("app.domain.fast_fail_gate.visual_quality_gate.VisualQualityValidator.validate", return_value=mock_visual):
            with open(dummy_video_file, "rb") as f:
                response = await async_client.post(
                    "/api/v1/claims/upload",
                    data={
                        "policy_id": "POL-HAPPY-001",
                        "capture_source": "FILE_UPLOAD",
                        "is_demo_rehearsal": "false",
                        "claim_description": "someone keyed my driver side door",
                    },
                    files={"video_file": ("test.mp4", f.read(), "video/mp4")},
                )

        assert response.status_code == 202
        res = response.json()
        assert res["passed"] is True
        assert res["claim_id"] is not None
        assert captured_intent_text == "someone keyed my driver side door"
