"""
tests/dual_mask_segmentation/test_som_crop_renderer.py
Verifies Set-of-Marks (SoM) Rendering and Zero-Occlusion Guarantees:
- T2-15: SoM non-occlusion invariant: verify rendered _som.jpg against _raw.jpg
         inside interior dmg_mask. 100% of pixels inside dmg_mask are bit-for-bit identical
         (0.00% damage surface occlusion), guaranteeing downstream VLM sees unaltered texture.
"""
from pathlib import Path
import uuid
import cv2
import numpy as np
import pytest

from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.som_crop_renderer import SoMCropRenderer
from tests.dual_mask_segmentation.conftest import (
    make_creta_oem_catalogue_record,
    make_test_candidate,
)


class TestSoMCropRenderer:
    @pytest.fixture
    def renderer(self, stage2_settings: Stage2Settings) -> SoMCropRenderer:
        return SoMCropRenderer(settings=stage2_settings)

    def test_t2_15_som_non_occlusion_invariant(
        self, renderer: SoMCropRenderer, synthetic_frame_1080p: np.ndarray
    ):
        """T2-15: Set-of-Marks Non-Occlusion Invariant:
        Rendered _som.jpg (annotated with exterior yellow dilated contour) and _raw.jpg
        must be bit-for-bit identical inside the interior damage mask.
        0% of damage surface pixels may be occluded by labels or contours, ensuring
        Stage 3 VLM receives pure, unaltered paint scratch/dent texture.
        """
        claim_id = uuid.uuid4()
        kf_key = "kf_01"
        loaded_frames = {kf_key: synthetic_frame_1080p}

        candidate = make_test_candidate(
            canonical_part_key="front_left_door",
            damage_classes=["dent"],
            final_iop_ratio=0.084,
            intersection=None,  # conftest default uses (400, 400, 600, 550) on 1080p
        )
        cat_rec = make_creta_oem_catalogue_record("front_left_door")

        grounded_parts = renderer.render_artifacts(
            claim_id=claim_id,
            candidates_with_cat=[(candidate, cat_rec)],
            loaded_frames_bgr=loaded_frames,
        )

        assert len(grounded_parts) == 1
        part = grounded_parts[0]

        # 1. Verify artifact files exist on disk
        assert part.som_raw_crop_path.exists(), f"Missing raw crop at {part.som_raw_crop_path}"
        assert part.som_annotated_crop_path.exists(), f"Missing SoM crop at {part.som_annotated_crop_path}"

        # 2. Read back generated crops
        raw_bgr = cv2.imread(str(part.som_raw_crop_path))
        som_bgr = cv2.imread(str(part.som_annotated_crop_path))
        assert raw_bgr is not None and som_bgr is not None
        assert raw_bgr.shape == som_bgr.shape, "Crop dimensions must match exactly"

        # 3. Reconstruct interior damage mask corresponding to crop ROI
        h_img, w_img = synthetic_frame_1080p.shape[:2]
        dmg_mask_full = np.zeros((h_img, w_img), dtype=np.uint8)
        vlm_hit = candidate.vlm_closeup_intersection
        cv_contours = renderer._geometry_to_cv_contours(vlm_hit.union_damage_polygon)
        cv2.fillPoly(dmg_mask_full, cv_contours, 255)

        xmin, ymin, xmax, ymax = [int(v) for v in vlm_hit.union_damage_polygon.bounds]
        bw, bh = max(1, xmax - xmin), max(1, ymax - ymin)
        pad_x = max(renderer.settings.som_min_padding_px, int(bw * renderer.settings.som_crop_padding_ratio))
        pad_y = max(renderer.settings.som_min_padding_px, int(bh * renderer.settings.som_crop_padding_ratio))
        cx1, cy1 = max(0, xmin - pad_x), max(0, ymin - pad_y)
        cx2, cy2 = min(w_img, xmax + pad_x), min(h_img, ymax + pad_y)

        crop_dmg_mask = dmg_mask_full[cy1:cy2, cx1:cx2]

        # Interior mask (interior of the damage surface, well within the 15px dilated bounding border)
        interior_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        interior_mask = cv2.erode(crop_dmg_mask, interior_kernel)

        total_interior_pixels = np.count_nonzero(interior_mask == 255)
        assert total_interior_pixels > 1000, "Interior damage mask must cover significant pixel area"

        # 4. Compare pixels between _raw.jpg and _som.jpg inside interior_mask
        diff = np.abs(raw_bgr.astype(int) - som_bgr.astype(int))
        occluded_pixels = np.count_nonzero(diff[interior_mask == 255])

        assert occluded_pixels == 0, (
            f"Expected 0 occluded pixels inside interior damage mask, but found {occluded_pixels} differing pixels."
        )

        # 5. Verify that exterior annotation actually exists on som_bgr outside dmg_mask
        exterior_diff = np.count_nonzero(diff[crop_dmg_mask == 0])
        assert exterior_diff > 0, "SoM crop must contain visible exterior yellow contour annotation"

        # 6. Verify SVG overlay structure
        svg = part.svg_overlay
        assert svg.view_box == f"0 0 {vlm_hit.width_px} {vlm_hit.height_px}"
        assert len(svg.part_svg_points_norm) >= 3
        assert len(svg.damage_svg_points_norm) >= 3
        for x_norm, y_norm in svg.damage_svg_points_norm:
            assert 0.0 <= x_norm <= 1.0
            assert 0.0 <= y_norm <= 1.0
