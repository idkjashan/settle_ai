"""
evals/dual_mask_segmentation/ci_gate_assertions.py
Production CI Gate Assertions for Stage 2 Dual-Mask Segmentation.

Validates the 5 Frozen Quantitative Invariants:
1. IoP Error <= 1.5%
2. Zoom Anti-Inflation Invariance (0.0% false replacements on macro closeups)
3. SQL Catalogue Hit Rate (100.0% on 22 canonical parts)
4. SoM Interior Occlusion Rate (0.00% pixels occluded)
5. Latency & SLA Guardrails (p50 <= 240ms, p95 <= 420ms)

Usage:
    python -m evals.dual_mask_segmentation.ci_gate_assertions
"""
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple
import uuid

# Inject ffmpeg path
_ffmpeg_dir = r"C:\Users\Hp\AppData\Local\ffmpeg\bin"
if os.path.exists(_ffmpeg_dir) and _ffmpeg_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{_ffmpeg_dir};{os.environ.get('PATH', '')}"

import cv2
import numpy as np
from sqlalchemy import select

from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.part_side_resolver_and_grouper import (
    PartSideResolverAndGrouper,
)
from app.domain.dual_mask_segmentation.polygon_intersection_engine import (
    PolygonIntersectionEngine,
)
from app.domain.dual_mask_segmentation.schemas import (
    FrameDualPredictions,
    GroupedPartCandidate,
    OEMPartCatalogueRecord,
    RawMaskPrediction,
)
from app.domain.dual_mask_segmentation.som_crop_renderer import SoMCropRenderer
from app.domain.dual_mask_segmentation.taxonomy import (
    CARPARTS_CLASS_MAP,
    IGNORED_PART_CLASSES,
)
from app.infrastructure.db.models import OEMPartsCatalogue
from tests.dual_mask_segmentation.conftest import (
    make_box_polygon_coords,
    make_creta_oem_catalogue_record,
    make_frame_predictions,
    make_raw_damage_prediction,
    make_raw_part_prediction,
    make_test_candidate,
)
from tests.in_memory_db import (
    FakeAsyncSession,
    in_memory_db,
    patch_in_memory_db,
)

patch_in_memory_db()


class Stage2CIGateSuite:
    """Automated CI Gate verification suite for Stage 2 invariants."""

    def __init__(self):
        in_memory_db.reset()
        self.tmp_dir = Path("/tmp/evals_stage2")
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.settings = Stage2Settings(som_output_dir=self.tmp_dir / "som")
        self.engine = PolygonIntersectionEngine(settings=self.settings)
        self.grouper = PartSideResolverAndGrouper(settings=self.settings)
        self.renderer = SoMCropRenderer(settings=self.settings)

    def evaluate_invariant_1_iop_error(self) -> float:
        """Invariant 1: IoP Measurement Error <= 1.5% across diverse geometric shapes."""
        print("\n[Gate 1] Evaluating IoP Error Invariant (Target <= 1.5%)...")
        errors: List[float] = []

        # Test 20 synthetic geometries with analytical ground-truth areas
        for i in range(1, 21):
            part_w = 400 + (i * 25)
            part_h = 200 + (i * 15)
            gt_part_area = float(part_w * part_h)

            dmg_w = int(part_w * (0.12 + i * 0.01))
            dmg_h = int(part_h * (0.15 + i * 0.015))
            gt_dmg_area = float(dmg_w * dmg_h)
            gt_iop = gt_dmg_area / gt_part_area

            p1 = make_raw_part_prediction(
                class_name="front_left_door",
                confidence=0.92,
                x1=100,
                y1=100,
                x2=100 + part_w,
                y2=100 + part_h,
            )
            d1 = make_raw_damage_prediction(
                class_name="dent",
                confidence=0.88,
                x1=150,
                y1=150,
                x2=150 + dmg_w,
                y2=150 + dmg_h,
            )

            frame = make_frame_predictions(
                keyframe_key=f"kf_eval_{i}",
                frame_path=Path(f"/tmp/kf_{i}.jpg"),
                frame_index=i,
                part_predictions=[p1],
                damage_predictions=[d1],
            )
            intersections, _, _ = self.engine.compute_intersections([frame])
            assert len(intersections) == 1, f"Trial {i} failed to compute intersection"
            measured_iop = intersections[0].raw_iop_ratio
            abs_err = abs(measured_iop - gt_iop)
            errors.append(abs_err)

        max_error = max(errors)
        mean_error = float(np.mean(errors))
        print(f"  -> Mean IoP Error: {mean_error * 100:.3f}%, Max IoP Error: {max_error * 100:.3f}%")
        assert max_error <= 0.015, f"IoP Error ceiling violated: max_error={max_error * 100:.3f}% > 1.5%"
        return max_error

    def evaluate_invariant_2_zoom_anti_inflation(self) -> float:
        """Invariant 2: Zoom Anti-Inflation Invariance:
        0.0% false replacements on macro closeups (final IoP clamped or locked to true unclipped area).
        """
        print("\n[Gate 2] Evaluating Zoom Anti-Inflation Invariance (Target: 0.0% false replacements)...")
        false_replacements = 0
        total_trials = 100

        # Sub-suite A: 50 Dual-frame trials (Medium unclipped shot + Zoomed closeup)
        for i in range(50):
            # Medium shot: door unclipped, true IoP = 0.035 (3.5%)
            p_med = make_raw_part_prediction(
                class_name="front_left_door",
                confidence=0.93,
                x1=200,
                y1=200,
                x2=1200,
                y2=400,  # 1000 x 200 = 200,000 px^2
            )
            d_med = make_raw_damage_prediction(
                class_name="dent",
                confidence=0.87,
                x1=250,
                y1=250,
                x2=350,
                y2=320,  # 100 x 70 = 7,000 px^2 -> true IoP = 0.035
            )
            f_med = make_frame_predictions(
                keyframe_key=f"kf_med_{i}",
                frame_path=Path(f"/tmp/med_{i}.jpg"),
                frame_index=1,
                laplacian_sharpness=120.0,
                part_predictions=[p_med],
                damage_predictions=[d_med],
            )

            # Zoomed shot: touches border (x1=0, y1=0), inflated raw IoP = 0.50 (50.0%)
            p_zoom = make_raw_part_prediction(
                class_name="front_left_door",
                confidence=0.96,
                x1=0,
                y1=0,
                x2=200,
                y2=100,  # 20,000 px^2
            )
            d_zoom = make_raw_damage_prediction(
                class_name="dent",
                confidence=0.92,
                x1=0,
                y1=0,
                x2=100,
                y2=100,  # 10,000 px^2 -> raw IoP = 0.50
            )
            f_zoom = make_frame_predictions(
                keyframe_key=f"kf_zoom_{i}",
                frame_path=Path(f"/tmp/zoom_{i}.jpg"),
                frame_index=2,
                laplacian_sharpness=280.0,
                part_predictions=[p_zoom],
                damage_predictions=[d_zoom],
            )

            intersections, _, unclipped = self.engine.compute_intersections([f_med, f_zoom])
            candidates = self.grouper.resolve_and_group(intersections, [f_med, f_zoom], unclipped)
            assert len(candidates) == 1
            cand = candidates[0]

            # Invariant: final_iop must lock to unclipped shot (0.035), not inflated zoom (0.50)
            if cand.final_iop_ratio > 0.25:
                false_replacements += 1

        # Sub-suite B: 50 Clipped-only macro closeup trials
        for i in range(50):
            p_macro = make_raw_part_prediction(
                class_name="front_left_door",
                confidence=0.88,
                x1=0,
                y1=0,
                x2=150,
                y2=150,  # 22,500 px^2
            )
            d_macro = make_raw_damage_prediction(
                class_name="dent",
                confidence=0.84,
                x1=0,
                y1=0,
                x2=120,
                y2=120,  # 14,400 px^2 -> raw IoP = 0.64
            )
            f_macro = make_frame_predictions(
                keyframe_key=f"kf_macro_{i}",
                frame_path=Path(f"/tmp/macro_{i}.jpg"),
                frame_index=1,
                laplacian_sharpness=240.0,
                part_predictions=[p_macro],
                damage_predictions=[d_macro],
            )

            intersections, _, _ = self.engine.compute_intersections([f_macro])
            candidates = self.grouper.resolve_and_group(intersections, [f_macro], unclipped_part_areas={})
            assert len(candidates) == 1
            cand = candidates[0]

            # Invariant: clipped-only shot MUST clamp to <= 0.25
            if cand.final_iop_ratio > 0.25:
                false_replacements += 1

        false_replacement_rate = float(false_replacements) / float(total_trials)
        print(f"  -> False Replacement Rate on Macro Closeups: {false_replacement_rate * 100:.2f}% (0 / {total_trials})")
        assert false_replacements == 0, f"Zoom Anti-Inflation violated: {false_replacements} false replacements"
        return false_replacement_rate

    async def evaluate_invariant_3_sql_catalogue_hit_rate(self) -> float:
        """Invariant 3: SQL Catalogue Hit Rate = 100.0% on 22 canonical vehicle body parts."""
        print("\n[Gate 3] Evaluating SQL OEM Catalogue Hit Rate (Target: 100.0% across 22 canonical parts)...")
        session = FakeAsyncSession()
        makes_models = [
            ("Hyundai", "Creta"),
            ("Maruti", "Swift"),
            ("Tata", "Nexon"),
        ]

        canonical_keys = [
            v for k, v in CARPARTS_CLASS_MAP.items() if v not in IGNORED_PART_CLASSES
        ]
        assert len(canonical_keys) == 22, f"Expected 22 canonical part classes, got {len(canonical_keys)}"

        total_queries = 0
        hits = 0

        for make, model in makes_models:
            for pkey in canonical_keys:
                total_queries += 1
                stmt = select(OEMPartsCatalogue).where(
                    OEMPartsCatalogue.make == make,
                    OEMPartsCatalogue.model == model,
                    OEMPartsCatalogue.canonical_part_key == pkey,
                )
                res = await session.execute(stmt)
                part_row = res.scalars().first()
                if part_row is not None:
                    assert part_row.canonical_part_key == pkey
                    assert float(part_row.oem_part_cost_inr) > 0.0
                    hits += 1

        hit_rate = float(hits) / float(total_queries)
        print(f"  -> SQL Catalogue Hits: {hits} / {total_queries} ({hit_rate * 100:.2f}%)")
        assert hits == total_queries, f"SQL Catalogue Hit Rate below 100.0%: {hits}/{total_queries}"
        return hit_rate

    def evaluate_invariant_4_som_interior_occlusion(self) -> float:
        """Invariant 4: SoM Interior Occlusion Rate = 0.00% (0 pixels occluded)."""
        print("\n[Gate 4] Evaluating SoM Interior Occlusion Invariant (Target: 0.00% occluded)...")
        total_interior_pixels = 0
        total_occluded_pixels = 0

        # Test across 20 distinct panel and damage geometries
        for i in range(1, 21):
            frame = np.full((1080, 1920, 3), 160 + (i % 20), dtype=np.uint8)
            claim_id = uuid.uuid4()
            kf_key = f"kf_{i:02d}"

            x1 = 200 + (i * 20)
            y1 = 200 + (i * 15)
            x2 = x1 + 180
            y2 = y1 + 120

            cand = make_test_candidate(
                canonical_part_key="front_left_door",
                damage_classes=["dent"],
                final_iop_ratio=0.084,
                intersection=None,
            )
            # Override intersection for variety
            cand.vlm_closeup_intersection.keyframe_key = kf_key
            cand.area_measurement_intersection.keyframe_key = kf_key
            vlm_box = (x1, y1, x2, y2)
            from shapely.geometry import box
            cand.vlm_closeup_intersection.union_damage_polygon = box(*vlm_box)
            cand.vlm_closeup_intersection.part_polygon = box(x1 - 100, y1 - 100, x2 + 500, y2 + 400)

            cat_rec = make_creta_oem_catalogue_record("front_left_door")

            grounded_parts = self.renderer.render_artifacts(
                claim_id=claim_id,
                candidates_with_cat=[(cand, cat_rec)],
                loaded_frames_bgr={kf_key: frame},
            )
            assert len(grounded_parts) == 1
            part = grounded_parts[0]

            raw = cv2.imread(str(part.som_raw_crop_path))
            som = cv2.imread(str(part.som_annotated_crop_path))

            # Reconstruct interior mask
            dmg_mask = np.zeros((1080, 1920), dtype=np.uint8)
            cv_contours = self.renderer._geometry_to_cv_contours(box(*vlm_box))
            cv2.fillPoly(dmg_mask, cv_contours, 255)

            bw, bh = max(1, x2 - x1), max(1, y2 - y1)
            pad_x = max(self.settings.som_min_padding_px, int(bw * self.settings.som_crop_padding_ratio))
            pad_y = max(self.settings.som_min_padding_px, int(bh * self.settings.som_crop_padding_ratio))
            cx1 = max(0, x1 - pad_x)
            cy1 = max(0, y1 - pad_y)
            cx2 = min(1920, x2 + pad_x)
            cy2 = min(1080, y2 + pad_y)

            crop_mask = dmg_mask[cy1:cy2, cx1:cx2]
            interior_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            interior_mask = cv2.erode(crop_mask, interior_kernel)

            diff = np.abs(raw.astype(int) - som.astype(int))
            occluded = np.count_nonzero(diff[interior_mask == 255])
            interior_px = np.count_nonzero(interior_mask == 255)

            total_interior_pixels += interior_px
            total_occluded_pixels += occluded

        occlusion_rate = float(total_occluded_pixels) / float(max(1, total_interior_pixels))
        print(f"  -> Evaluated Interior Pixels: {total_interior_pixels:,}")
        print(f"  -> Occluded Pixels: {total_occluded_pixels} ({occlusion_rate * 100:.4f}%)")
        assert total_occluded_pixels == 0, f"SoM occlusion invariant violated: {total_occluded_pixels} occluded pixels"
        return occlusion_rate

    async def evaluate_invariant_5_latency_guardrails(self) -> Tuple[float, float]:
        """Invariant 5: Latency & SLA Guardrails:
        p50 <= 240 ms, p95 <= 420 ms across 40 benchmark iterations.
        """
        print("\n[Gate 5] Evaluating Latency & SLA Guardrails (Target: p50 <= 240ms, p95 <= 420ms)...")
        latencies_ms: List[float] = []
        frame_bgr = np.zeros((1080, 1920, 3), dtype=np.uint8)

        # Prebuild input objects
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
        frame_preds = [
            make_frame_predictions(
                keyframe_key=f"kf_01",
                frame_path=Path("/tmp/kf_01.jpg"),
                frame_index=1,
                part_predictions=[p_door],
                damage_predictions=[d_dent],
            ),
            make_frame_predictions(
                keyframe_key=f"kf_02",
                frame_path=Path("/tmp/kf_02.jpg"),
                frame_index=2,
                part_predictions=[p_door],
                damage_predictions=[d_dent],
            ),
        ]
        loaded_frames = {"kf_01": frame_bgr, "kf_02": frame_bgr}

        from app.domain.dual_mask_segmentation.catalog_and_ledger_grounder import CatalogAndLedgerGrounder
        session = FakeAsyncSession()
        grounder = CatalogAndLedgerGrounder(db_session=session, settings=self.settings)

        # Warmup
        for _ in range(5):
            intersections, _, unclipped = self.engine.compute_intersections(frame_preds)
            cands = self.grouper.resolve_and_group(intersections, frame_preds, unclipped)
            res = await grounder.ground_and_check_guardrails("POL-HAPPY-001", cands)
            _ = self.renderer.render_artifacts(uuid.uuid4(), res.verified_pairs, loaded_frames)

        # Benchmark 40 iterations
        for _ in range(40):
            t0 = time.perf_counter()
            intersections, _, unclipped = self.engine.compute_intersections(frame_preds)
            cands = self.grouper.resolve_and_group(intersections, frame_preds, unclipped)
            res = await grounder.ground_and_check_guardrails("POL-HAPPY-001", cands)
            _ = self.renderer.render_artifacts(uuid.uuid4(), res.verified_pairs, loaded_frames)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies_ms.append(elapsed_ms)

        p50 = float(np.percentile(latencies_ms, 50))
        p95 = float(np.percentile(latencies_ms, 95))
        p99 = float(np.percentile(latencies_ms, 99))
        print(f"  -> Measured Latency Distribution (n=40):")
        print(f"     p50: {p50:.2f} ms (Target <= 240.0 ms)")
        print(f"     p95: {p95:.2f} ms (Target <= 420.0 ms)")
        print(f"     p99: {p99:.2f} ms")

        assert p50 <= 240.0, f"SLA Violation: p50={p50:.2f}ms > 240.0ms ceiling"
        assert p95 <= 420.0, f"SLA Violation: p95={p95:.2f}ms > 420.0ms ceiling"
        return p50, p95

    async def run_all(self) -> bool:
        """Executes all 5 CI gate quantitative invariant evaluations."""
        print("=================================================================")
        print("STAGE 2 DUAL-MASK SEGMENTATION: CI GATE ASSERTIONS & INVARIANTS")
        print("=================================================================")

        t_start = time.perf_counter()
        _ = self.evaluate_invariant_1_iop_error()
        _ = self.evaluate_invariant_2_zoom_anti_inflation()
        _ = await self.evaluate_invariant_3_sql_catalogue_hit_rate()
        _ = self.evaluate_invariant_4_som_interior_occlusion()
        p50, p95 = await self.evaluate_invariant_5_latency_guardrails()

        total_sec = time.perf_counter() - t_start
        print("\n=================================================================")
        print(f"ALL 5 CI GATE INVARIANTS PASSED SUCCESSFULLY IN {total_sec:.2f}s")
        print(f"  1. IoP Error <= 1.5%                     : PASS")
        print(f"  2. Zoom Anti-Inflation (0.0% replacements): PASS")
        print(f"  3. SQL Catalogue Hit Rate (100.0%)       : PASS")
        print(f"  4. SoM Interior Occlusion (0.00%)        : PASS")
        print(f"  5. Latency & SLA (p50={p50:.1f}ms, p95={p95:.1f}ms): PASS")
        print("=================================================================\n")
        return True


def main() -> int:
    suite = Stage2CIGateSuite()
    try:
        success = asyncio.run(suite.run_all())
        return 0 if success else 1
    except Exception as e:
        print(f"\n[FATAL CI GATE FAILURE] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
