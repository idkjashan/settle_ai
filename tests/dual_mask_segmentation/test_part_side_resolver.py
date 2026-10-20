"""
tests/dual_mask_segmentation/test_part_side_resolver.py
Verifies Part Side Resolution and Walkaround Trajectory Inference:
- T2-08: Generic 'front_door' resolved to 'front_left_door' via left-side trajectory window.
- T2-09: Generic 'back_door' fallback when no side cues exist.
"""
from pathlib import Path
import pytest

from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.part_side_resolver_and_grouper import (
    PartSideResolverAndGrouper,
)
from app.domain.dual_mask_segmentation.schemas import (
    FrameDualPredictions,
    PartDamageIntersection,
)
from tests.dual_mask_segmentation.conftest import (
    make_frame_predictions,
    make_raw_damage_prediction,
    make_raw_part_prediction,
    make_test_intersection,
)


class TestPartSideResolver:
    @pytest.fixture
    def grouper(self, stage2_settings: Stage2Settings) -> PartSideResolverAndGrouper:
        return PartSideResolverAndGrouper(settings=stage2_settings)

    def test_t2_08_generic_front_door_resolved_to_left_via_trajectory(
        self, grouper: PartSideResolverAndGrouper
    ):
        """T2-08: When Carparts-Seg predicts a generic 'front_door', but surrounding
        keyframes in the walkaround trajectory contain clear left-side indicators
        ('left_mirror' or 'front_left_light'), the grouper resolves 'front_door' to
        'front_left_door' with method 'TRAJECTORY_PROPAGATED_LEFT'.
        """
        # Frame 0: Left mirror detected with high confidence -> marks Frame 0 as LEFT side
        p_mirror = make_raw_part_prediction(
            class_name="left_mirror",
            confidence=0.88,
            x1=100,
            y1=100,
            x2=200,
            y2=200,
        )
        frame_0 = make_frame_predictions(
            keyframe_key="kf_00",
            frame_path=Path("/tmp/kf_00.jpg"),
            frame_index=0,
            part_predictions=[p_mirror],
            damage_predictions=[],
        )

        # Frame 1: Generic 'front_door' prediction with damage
        p_door = make_raw_part_prediction(
            class_name="front_door",
            confidence=0.86,
            x1=200,
            y1=100,
            x2=800,
            y2=600,
        )
        d_dent = make_raw_damage_prediction(
            class_name="dent",
            confidence=0.84,
            x1=300,
            y1=200,
            x2=450,
            y2=350,
        )
        frame_1 = make_frame_predictions(
            keyframe_key="kf_01",
            frame_path=Path("/tmp/kf_01.jpg"),
            frame_index=1,
            part_predictions=[p_door],
            damage_predictions=[d_dent],
        )

        # Frame 2: Confirming persistence on front_door
        frame_2 = make_frame_predictions(
            keyframe_key="kf_02",
            frame_path=Path("/tmp/kf_02.jpg"),
            frame_index=2,
            part_predictions=[p_door],
            damage_predictions=[d_dent],
        )

        hit_1 = make_test_intersection(
            keyframe_key="kf_01",
            frame_index=1,
            part_class="front_door",
            damage_classes=["dent"],
            damage_confidence=0.84,
            part_confidence=0.86,
        )
        hit_2 = make_test_intersection(
            keyframe_key="kf_02",
            frame_index=2,
            part_class="front_door",
            damage_classes=["dent"],
            damage_confidence=0.84,
            part_confidence=0.86,
        )

        candidates = grouper.resolve_and_group(
            intersections=[hit_1, hit_2],
            predictions=[frame_0, frame_1, frame_2],
            unclipped_part_areas={},
        )

        assert len(candidates) == 1
        cand = candidates[0]
        # Resolved from generic front_door to front_left_door!
        assert cand.canonical_part_key == "front_left_door"
        assert cand.side_resolution_method == "TRAJECTORY_PROPAGATED_LEFT"
        assert cand.raw_detected_part_classes == ["front_door"]

    def test_t2_09_generic_back_door_fallback_without_side_cues(
        self, grouper: PartSideResolverAndGrouper
    ):
        """T2-09: When Carparts-Seg predicts a generic 'back_door' and no side cues
        exist in the walkaround trajectory (symmetric or absent contextual parts),
        the grouper safely falls back to the generic key 'back_door' with method
        'GENERIC_FALLBACK_KEY', which matches the generic OEM alias in the catalogue.
        """
        # Frames 1 and 2 only contain generic back_door with no side cues
        p_back_door = make_raw_part_prediction(
            class_name="back_door",
            confidence=0.87,
            x1=200,
            y1=100,
            x2=800,
            y2=600,
        )
        d_scratch = make_raw_damage_prediction(
            class_name="scratch",
            confidence=0.82,
            x1=300,
            y1=200,
            x2=500,
            y2=250,
        )

        frame_1 = make_frame_predictions(
            keyframe_key="kf_01",
            frame_path=Path("/tmp/kf_01.jpg"),
            frame_index=1,
            part_predictions=[p_back_door],
            damage_predictions=[d_scratch],
        )
        frame_2 = make_frame_predictions(
            keyframe_key="kf_02",
            frame_path=Path("/tmp/kf_02.jpg"),
            frame_index=2,
            part_predictions=[p_back_door],
            damage_predictions=[d_scratch],
        )

        hit_1 = make_test_intersection(
            keyframe_key="kf_01",
            frame_index=1,
            part_class="back_door",
            damage_classes=["scratch"],
            damage_confidence=0.82,
            part_confidence=0.87,
        )
        hit_2 = make_test_intersection(
            keyframe_key="kf_02",
            frame_index=2,
            part_class="back_door",
            damage_classes=["scratch"],
            damage_confidence=0.82,
            part_confidence=0.87,
        )

        candidates = grouper.resolve_and_group(
            intersections=[hit_1, hit_2],
            predictions=[frame_1, frame_2],
            unclipped_part_areas={},
        )

        assert len(candidates) == 1
        cand = candidates[0]
        # Maintained generic alias
        assert cand.canonical_part_key == "back_door"
        assert cand.side_resolution_method == "GENERIC_FALLBACK_KEY"
