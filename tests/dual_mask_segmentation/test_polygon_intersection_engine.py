"""
tests/dual_mask_segmentation/test_polygon_intersection_engine.py
Verifies GEOS spatial geometry operations:
- T2-02: Class 18 'object' ignored / filtered out
- T2-03: 10% Boundary spillover rejection (bleed onto adjacent panel discarded)
- T2-04: Stacked damage unary_union (preventing double counting of co-located damages)
- T2-05: Thin key scratch floor tolerance (retaining linear damage >= 0.003)
- T2-14: Self-intersecting bow-tie polygon healing via .buffer(0)
"""
from pathlib import Path
import numpy as np
import pytest
from shapely.geometry import Polygon

from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.polygon_intersection_engine import (
    PolygonIntersectionEngine,
)
from app.domain.dual_mask_segmentation.schemas import (
    FrameDualPredictions,
    RawMaskPrediction,
)
from tests.dual_mask_segmentation.conftest import (
    make_box_polygon_coords,
    make_frame_predictions,
    make_raw_damage_prediction,
    make_raw_part_prediction,
)


class TestPolygonIntersectionEngine:
    @pytest.fixture
    def engine(self, stage2_settings: Stage2Settings) -> PolygonIntersectionEngine:
        return PolygonIntersectionEngine(settings=stage2_settings)

    def test_t2_02_class_18_object_filter_ignored(self, engine: PolygonIntersectionEngine):
        """T2-02: Carparts-Seg Class 18 ('object') must be strictly filtered out and never
        participate in damage grounding or cause false escalations.
        """
        # Create an 'object' part prediction with high confidence overlapping a dent
        object_part = make_raw_part_prediction(
            class_name="object",
            confidence=0.91,
            x1=200,
            y1=200,
            x2=800,
            y2=800,
        )
        damage = make_raw_damage_prediction(
            class_name="dent",
            confidence=0.88,
            x1=300,
            y1=300,
            x2=500,
            y2=500,
        )

        frame_pred = make_frame_predictions(
            keyframe_key="kf_01",
            frame_path=Path("/tmp/kf_01.jpg"),
            frame_index=1,
            part_predictions=[object_part],
            damage_predictions=[damage],
        )

        intersections, discarded_hits, unclipped = engine.compute_intersections([frame_pred])

        assert len(intersections) == 0, "Class 18 'object' should yield zero valid intersections"
        assert len(unclipped) == 0, "'object' must not be recorded in unclipped_part_areas"

    def test_t2_03_boundary_spillover_rejection(self, engine: PolygonIntersectionEngine):
        """T2-03: Boundary spillover rejection:
        A damage of 10,000 px^2 has 97% overlap on front_left_door (9,700 px^2)
        and 3% spillover on adjacent front_bumper (300 px^2).
        The 3% bleed must be discarded with SPILLOVER_BELOW_10_PERCENT, while the
        door intersection is accepted.
        """
        # Door: [100, 100, 600, 700] (area = 500 * 600 = 300,000 px^2)
        # Bumper: [597, 100, 1100, 700] (area = 503 * 600 = 301,800 px^2)
        # Damage: [500, 300, 600, 400] (width = 100, height = 100, total area = 10,000 px^2)
        # Overlap with door: [500..597] x [300..400] -> width 97, height 100 = 9,700 px^2 (97%)
        # Overlap with bumper: [597..600] x [300..400] -> width 3, height 100 = 300 px^2 (3%)
        door_part = make_raw_part_prediction(
            class_name="front_left_door",
            confidence=0.94,
            x1=100,
            y1=100,
            x2=597,
            y2=700,
        )
        bumper_part = make_raw_part_prediction(
            class_name="front_bumper",
            confidence=0.91,
            x1=597,
            y1=100,
            x2=1100,
            y2=700,
        )
        damage = make_raw_damage_prediction(
            class_name="dent",
            confidence=0.89,
            x1=500,
            y1=300,
            x2=600,
            y2=400,
        )

        frame_pred = make_frame_predictions(
            keyframe_key="kf_01",
            frame_path=Path("/tmp/kf_01.jpg"),
            frame_index=1,
            part_predictions=[door_part, bumper_part],
            damage_predictions=[damage],
        )

        intersections, discarded_hits, _ = engine.compute_intersections([frame_pred])

        # Door intersection is retained
        assert len(intersections) == 1
        accepted = intersections[0]
        assert accepted.raw_part_class == "front_left_door"
        assert accepted.union_damage_intersection_area_px == pytest.approx(9700.0, rel=1e-2)

        # Bumper bleed of 3% is discarded
        assert len(discarded_hits) == 1
        disc = discarded_hits[0]
        assert disc.part_class == "front_bumper"
        assert disc.damage_class == "dent"
        assert disc.spillover_ratio == pytest.approx(0.03, abs=0.005)
        assert disc.reason == "SPILLOVER_BELOW_10_PERCENT"

    def test_t2_04_stacked_damage_unary_union(self, engine: PolygonIntersectionEngine):
        """T2-04: Stacked co-located damage unary_union:
        A dent of 8,000 px^2 and a scratch of 4,000 px^2 co-located inside the dent
        on a panel of 100,000 px^2 must produce a merged union of 8,000 px^2 (IoP=0.080 / 8.0%),
        preventing double-counting (which would erroneously produce 12,000 px^2 / 12.0%).
        """
        # Door panel: area = 1000 * 100 = 100,000 px^2
        door_part = make_raw_part_prediction(
            class_name="front_left_door",
            confidence=0.95,
            x1=100,
            y1=100,
            x2=1100,
            y2=200,
        )
        # Dent: [200, 100, 300, 180] -> 100 x 80 = 8,000 px^2
        dent = make_raw_damage_prediction(
            class_name="dent",
            confidence=0.86,
            x1=200,
            y1=100,
            x2=300,
            y2=180,
        )
        # Scratch completely inside dent: [210, 110, 260, 190] clamped to [210, 110, 260, 180]
        # Let's explicitly define scratch inside the dent: width 50, height 80 = 4,000 px^2
        scratch = make_raw_damage_prediction(
            class_name="scratch",
            confidence=0.82,
            x1=210,
            y1=100,
            x2=260,
            y2=180,
        )

        frame_pred = make_frame_predictions(
            keyframe_key="kf_01",
            frame_path=Path("/tmp/kf_01.jpg"),
            frame_index=1,
            part_predictions=[door_part],
            damage_predictions=[dent, scratch],
        )

        intersections, _, _ = engine.compute_intersections([frame_pred])

        assert len(intersections) == 1
        inter = intersections[0]
        # Union area must equal 8,000 px^2 (the dent bounding the scratch)
        assert inter.union_damage_intersection_area_px == pytest.approx(8000.0, rel=1e-2)
        # Raw IoP must be 8,000 / 100,000 = 0.080, NOT 0.120!
        assert inter.raw_iop_ratio == pytest.approx(0.080, abs=1e-3)
        assert set(inter.damage_classes) == {"dent", "scratch"}
        # Actuarial severity priority selects dent (priority 5) over scratch (priority 6)
        assert inter.primary_damage_class == "dent"

    def test_t2_05_thin_key_scratch_retained_vs_areal_floor(self, engine: PolygonIntersectionEngine):
        """T2-05: Linear damage class floor tolerance:
        A thin key scratch with IoP = 0.005 (0.5%) on a 100,000 px^2 panel exceeds the
        linear floor (0.003 / 0.3%) and must be retained.
        An areal damage (dent) with the exact same IoP = 0.005 falls below the areal
        floor (0.008 / 0.8%) and must be filtered out.
        """
        # Door panel: 1000 * 100 = 100,000 px^2
        door_part = make_raw_part_prediction(
            class_name="front_left_door",
            confidence=0.92,
            x1=100,
            y1=100,
            x2=1100,
            y2=200,
        )
        # Scratch: area = 500 px^2 -> IoP = 500 / 100,000 = 0.005 (>= 0.003 floor)
        scratch = make_raw_damage_prediction(
            class_name="scratch",
            confidence=0.85,
            x1=200,
            y1=100,
            x2=700,
            y2=101,  # 500 x 1 = 500 px^2
        )

        frame_scratch = make_frame_predictions(
            keyframe_key="kf_scratch",
            frame_path=Path("/tmp/kf_s.jpg"),
            frame_index=1,
            part_predictions=[door_part],
            damage_predictions=[scratch],
        )
        intersections_s, _, _ = engine.compute_intersections([frame_scratch])
        assert len(intersections_s) == 1, "Thin scratch with IoP=0.005 must be retained"
        assert intersections_s[0].raw_iop_ratio == pytest.approx(0.005, abs=1e-4)

        # Same 500 px^2 damage as a dent
        dent = make_raw_damage_prediction(
            class_name="dent",
            confidence=0.85,
            x1=200,
            y1=100,
            x2=700,
            y2=101,
        )
        frame_dent = make_frame_predictions(
            keyframe_key="kf_dent",
            frame_path=Path("/tmp/kf_d.jpg"),
            frame_index=2,
            part_predictions=[door_part],
            damage_predictions=[dent],
        )
        intersections_d, _, _ = engine.compute_intersections([frame_dent])
        assert len(intersections_d) == 0, "Dent with IoP=0.005 (< 0.008 areal floor) must be filtered out"

    def test_t2_14_self_intersecting_bow_tie_healed(self, engine: PolygonIntersectionEngine):
        """T2-14: Self-intersecting bow-tie polygon from segmentation edge artifacts
        must be gracefully healed via .buffer(0) without crashing the pipeline.
        """
        # Bow-tie polygon vertices: self-intersects in the middle
        bowtie_pts = np.array(
            [[100.0, 100.0], [300.0, 300.0], [100.0, 300.0], [300.0, 100.0]],
            dtype=np.float32,
        )
        raw_poly = Polygon(bowtie_pts)
        assert not raw_poly.is_valid, "Bow-tie shape must initially be invalid"

        # Sanitize polygon heals self-intersection
        healed = engine.sanitize_polygon(bowtie_pts, min_area_px=50.0)
        assert healed is not None
        assert healed.is_valid, "Healed geometry must be valid"
        assert healed.area > 50.0

        # Execute in full compute_intersections pipeline with bow-tie damage mask
        door_part = make_raw_part_prediction(
            class_name="front_left_door",
            confidence=0.90,
            x1=50,
            y1=50,
            x2=500,
            y2=500,
        )
        bowtie_damage = RawMaskPrediction(
            class_id=0,
            class_name="dent",
            confidence=0.84,
            bbox_xyxy=(100, 100, 300, 300),
            polygon_xy_px=bowtie_pts,
        )
        frame_pred = make_frame_predictions(
            keyframe_key="kf_bowtie",
            frame_path=Path("/tmp/kf_bowtie.jpg"),
            frame_index=1,
            part_predictions=[door_part],
            damage_predictions=[bowtie_damage],
        )

        intersections, _, _ = engine.compute_intersections([frame_pred])
        assert len(intersections) == 1, "Healed polygon must successfully compute intersection"
        assert intersections[0].union_damage_intersection_area_px > 0.0
