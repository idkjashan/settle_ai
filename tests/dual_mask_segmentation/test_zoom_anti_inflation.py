"""
tests/dual_mask_segmentation/test_zoom_anti_inflation.py
Verifies Camera Zoom Anti-Inflation Defenses:
- T2-06: Dual-frame split: Medium shot (unclipped panel, IoP=0.032) vs Zoomed shot
         (clipped panel, raw IoP=0.46). Checks is_complete_panel=False on zoomed shot,
         locks final IoP to 0.032 from medium shot while directing VLM to zoomed crop.
- T2-07: Zoom anti-inflation clipped-only clamp: When damage is only captured on
         clipped closeup frames, IoP is clamped to <= 0.25 preventing false replacement.
"""
from pathlib import Path
import pytest
from shapely.geometry import box

from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.part_side_resolver_and_grouper import (
    PartSideResolverAndGrouper,
)
from app.domain.dual_mask_segmentation.polygon_intersection_engine import (
    PolygonIntersectionEngine,
)
from tests.dual_mask_segmentation.conftest import (
    make_frame_predictions,
    make_raw_damage_prediction,
    make_raw_part_prediction,
)


class TestZoomAntiInflation:
    @pytest.fixture
    def engine(self, stage2_settings: Stage2Settings) -> PolygonIntersectionEngine:
        return PolygonIntersectionEngine(settings=stage2_settings)

    @pytest.fixture
    def grouper(self, stage2_settings: Stage2Settings) -> PartSideResolverAndGrouper:
        return PartSideResolverAndGrouper(settings=stage2_settings)

    def test_t2_06_zoom_anti_inflation_dual_frame_split(
        self, engine: PolygonIntersectionEngine, grouper: PartSideResolverAndGrouper
    ):
        """T2-06: Decouple Area Measurement Frame from Macro Inspection Frame:
        Frame 1 (Medium shot): Unclipped door (100,000 px^2), damage (3,200 px^2), IoP = 0.032 (3.2%).
        Frame 2 (Zoomed closeup): Clipped door (20,000 px^2 visible), damage (9,200 px^2), raw IoP = 0.46 (46.0%).
        The engine flags Frame 2 as is_complete_panel=False.
        The grouper locks final_iop_ratio to 0.032 from Frame 1, avoiding false replacement (which triggers at >30%),
        while selecting Frame 2 as vlm_closeup_intersection for optimal visual clarity.
        """
        # Frame 1 (1920x1080): Door well clear of 15px border margin
        # Door: [200, 200, 1200, 300] -> width 1000, height 100 = 100,000 px^2
        # Damage: [300, 200, 340, 280] -> width 40, height 80 = 3,200 px^2 -> IoP = 0.032
        p1 = make_raw_part_prediction(
            class_name="front_left_door",
            confidence=0.92,
            x1=200,
            y1=200,
            x2=1200,
            y2=300,
        )
        d1 = make_raw_damage_prediction(
            class_name="dent",
            confidence=0.86,
            x1=300,
            y1=200,
            x2=340,
            y2=280,
        )
        frame_1 = make_frame_predictions(
            keyframe_key="kf_01",
            frame_path=Path("/tmp/kf_01.jpg"),
            frame_index=1,
            width_px=1920,
            height_px=1080,
            laplacian_sharpness=120.0,
            part_predictions=[p1],
            damage_predictions=[d1],
        )

        # Frame 2 (1920x1080): Macro shot touching the border (x1=0, y1=0)
        # Visible door: [0, 0, 200, 100] -> area = 20,000 px^2
        # Damage: [0, 0, 92, 100] -> area = 9,200 px^2 -> raw IoP = 9,200 / 20,000 = 0.46
        p2 = make_raw_part_prediction(
            class_name="front_left_door",
            confidence=0.95,
            x1=0,
            y1=0,
            x2=200,
            y2=100,
        )
        d2 = make_raw_damage_prediction(
            class_name="dent",
            confidence=0.92,
            x1=0,
            y1=0,
            x2=92,
            y2=100,
        )
        frame_2 = make_frame_predictions(
            keyframe_key="kf_02",
            frame_path=Path("/tmp/kf_02.jpg"),
            frame_index=2,
            width_px=1920,
            height_px=1080,
            laplacian_sharpness=260.0,
            part_predictions=[p2],
            damage_predictions=[d2],
        )

        intersections, _, unclipped_areas = engine.compute_intersections([frame_1, frame_2])

        assert len(intersections) == 2
        hit_1 = next(h for h in intersections if h.keyframe_key == "kf_01")
        hit_2 = next(h for h in intersections if h.keyframe_key == "kf_02")

        # Invariant: Completeness detection
        assert hit_1.is_complete_panel is True
        assert hit_1.raw_iop_ratio == pytest.approx(0.032, abs=1e-3)

        assert hit_2.is_complete_panel is False
        assert hit_2.raw_iop_ratio == pytest.approx(0.460, abs=1e-3)

        # Grouping and zoom anti-inflation resolution
        candidates = grouper.resolve_and_group(intersections, [frame_1, frame_2], unclipped_areas)
        assert len(candidates) == 1
        cand = candidates[0]

        assert cand.canonical_part_key == "front_left_door"
        # Must lock to unclipped medium shot IoP of 0.032, NOT 0.46!
        assert cand.final_iop_ratio == pytest.approx(0.032, abs=1e-3)
        assert cand.iop_estimation_method == "UNCLIPPED_COMPLETE_PANEL"
        assert cand.zoom_clipped_frames_filtered == 1

        # Decoupled keyframes:
        # Area measurement frame -> kf_01 (unclipped)
        # VLM closeup frame -> kf_02 (highest damage scale / macro detail)
        assert cand.area_measurement_intersection.keyframe_key == "kf_01"
        assert cand.vlm_closeup_intersection.keyframe_key == "kf_02"

    def test_t2_07_zoom_anti_inflation_clipped_only_clamp(
        self, engine: PolygonIntersectionEngine, grouper: PartSideResolverAndGrouper
    ):
        """T2-07: When a scratch or damage is only captured on zoom-clipped frames
        (no complete panel shot available), the grouper clamps the estimated IoP to
        <= 0.25 (25.0%), strictly preventing false part replacement.
        """
        # Single closeup frame touching border (x1=0, y1=0)
        # Door: [0, 0, 100, 100] -> area = 10,000 px^2
        # Damage: [0, 0, 80, 100] -> area = 8,000 px^2 -> raw IoP = 0.80 (80.0%)
        # High confidence so single_frame_override passes (p_conf=0.88 >= 0.80, d_conf=0.85 >= 0.75)
        p_clipped = make_raw_part_prediction(
            class_name="front_left_door",
            confidence=0.88,
            x1=0,
            y1=0,
            x2=100,
            y2=100,
        )
        d_clipped = make_raw_damage_prediction(
            class_name="scratch",
            confidence=0.85,
            x1=0,
            y1=0,
            x2=80,
            y2=100,
        )
        frame_clipped = make_frame_predictions(
            keyframe_key="kf_macro",
            frame_path=Path("/tmp/kf_macro.jpg"),
            frame_index=1,
            width_px=1920,
            height_px=1080,
            laplacian_sharpness=220.0,
            part_predictions=[p_clipped],
            damage_predictions=[d_clipped],
        )

        intersections, _, unclipped_areas = engine.compute_intersections([frame_clipped])
        assert len(intersections) == 1
        assert intersections[0].is_complete_panel is False
        assert intersections[0].raw_iop_ratio == pytest.approx(0.80, abs=1e-3)

        candidates = grouper.resolve_and_group(intersections, [frame_clipped], unclipped_part_areas={})
        assert len(candidates) == 1
        cand = candidates[0]

        # Raw IoP scaled by 0.35: 0.80 * 0.35 = 0.28, then clamped to capped floor 0.25
        assert cand.final_iop_ratio <= 0.25
        assert cand.final_iop_ratio == pytest.approx(0.25, abs=1e-4)
        assert cand.iop_estimation_method == "CLIPPED_PANEL_CLAMPED"
