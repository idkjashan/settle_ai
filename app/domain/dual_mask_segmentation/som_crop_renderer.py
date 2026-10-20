import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import cv2
import numpy as np
from shapely.geometry import MultiPolygon, Polygon

from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.schemas import (
    GroundedDamagedPart,
    GroupedPartCandidate,
    OEMPartCatalogueRecord,
    SVGOverlayPayload,
)


class SoMCropRenderer:
    """Renders Set-of-Marks (SoM) crops for Stage 3 with a 15px exterior dilated contour
    (guaranteeing 0% occlusion of interior damage pixels) and exports normalized SVG paths.
    """

    def __init__(self, settings: Optional[Stage2Settings] = None):
        self.settings = settings or Stage2Settings()

    @staticmethod
    def _geometry_to_cv_contours(geom) -> List[np.ndarray]:
        contours: List[np.ndarray] = []
        if isinstance(geom, Polygon):
            pts = np.array(geom.exterior.coords, dtype=np.int32).reshape((-1, 1, 2))
            contours.append(pts)
        elif isinstance(geom, MultiPolygon):
            for sub in geom.geoms:
                pts = np.array(sub.exterior.coords, dtype=np.int32).reshape((-1, 1, 2))
                contours.append(pts)
        return contours

    def _normalize_svg_points(
        self, geom, width_px: int, height_px: int
    ) -> List[Tuple[float, float]]:
        simplified = geom.simplify(self.settings.svg_simplify_tolerance_px, preserve_topology=True)
        if isinstance(simplified, MultiPolygon):
            simplified = max(simplified.geoms, key=lambda g: g.area)
        if not isinstance(simplified, Polygon) or simplified.is_empty:
            return []
        return [
            (round(float(x) / max(1, width_px), 4), round(float(y) / max(1, height_px), 4))
            for x, y in simplified.exterior.coords
        ]

    def render_artifacts(
        self,
        claim_id: UUID,
        candidates_with_cat: List[Tuple[GroupedPartCandidate, OEMPartCatalogueRecord]],
        loaded_frames_bgr: Dict[str, np.ndarray],
    ) -> List[GroundedDamagedPart]:
        claim_som_dir = self.settings.som_output_dir / str(claim_id)
        claim_som_dir.mkdir(parents=True, exist_ok=True)

        grounded_parts: List[GroundedDamagedPart] = []

        for idx, (cand, cat_rec) in enumerate(candidates_with_cat, start=1):
            vlm_hit = cand.vlm_closeup_intersection
            area_hit = cand.area_measurement_intersection
            frame_bgr = loaded_frames_bgr[vlm_hit.keyframe_key]
            h_img, w_img = frame_bgr.shape[:2]

            # 1. Rasterize union damage mask & dilate outward by 15px
            dmg_mask = np.zeros((h_img, w_img), dtype=np.uint8)
            cv_contours = self._geometry_to_cv_contours(vlm_hit.union_damage_polygon)
            cv2.fillPoly(dmg_mask, cv_contours, 255)

            r = self.settings.som_contour_dilation_px
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
            dilated_mask = cv2.dilate(dmg_mask, kernel, iterations=1)
            ext_contours, _ = cv2.findContours(dilated_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # 2. Compute padded crop bounds around dilated region
            xmin, ymin, xmax, ymax = [int(v) for v in vlm_hit.union_damage_polygon.bounds]
            bw = max(1, xmax - xmin)
            bh = max(1, ymax - ymin)
            pad_x = max(self.settings.som_min_padding_px, int(bw * self.settings.som_crop_padding_ratio))
            pad_y = max(self.settings.som_min_padding_px, int(bh * self.settings.som_crop_padding_ratio))

            cx1 = max(0, xmin - pad_x)
            cy1 = max(0, ymin - pad_y)
            cx2 = min(w_img, xmax + pad_x)
            cy2 = min(h_img, ymax + pad_y)

            # 3. Save clean raw crop and exterior-annotated SoM crop atomically
            raw_crop = frame_bgr[cy1:cy2, cx1:cx2].copy()
            annotated_full = frame_bgr.copy()
            cv2.drawContours(annotated_full, ext_contours, -1, (255, 255, 0), thickness=2, lineType=cv2.LINE_AA)

            label = f"[#{idx} {cand.canonical_part_key.upper()} | {cand.primary_damage_class.upper()}]"
            label_y = max(24, ymin - r - 10)
            cv2.putText(
                annotated_full,
                label,
                (max(10, xmin - r), label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 0),
                2,
                cv2.LINE_AA,
            )
            som_crop = annotated_full[cy1:cy2, cx1:cx2].copy()

            raw_path = claim_som_dir / f"{cand.canonical_part_key}_raw.jpg"
            som_path = claim_som_dir / f"{cand.canonical_part_key}_som.jpg"
            self._atomic_imwrite(raw_path, raw_crop)
            self._atomic_imwrite(som_path, som_crop)

            # 4. Build normalized SVG overlay from the unclipped measurement frame
            svg_overlay = SVGOverlayPayload(
                keyframe_key=area_hit.keyframe_key,
                view_box=f"0 0 {area_hit.width_px} {area_hit.height_px}",
                part_svg_points_norm=self._normalize_svg_points(
                    area_hit.part_polygon, area_hit.width_px, area_hit.height_px
                ),
                damage_svg_points_norm=self._normalize_svg_points(
                    area_hit.union_damage_polygon, area_hit.width_px, area_hit.height_px
                ),
            )

            grounded_parts.append(
                GroundedDamagedPart(
                    canonical_part_key=cand.canonical_part_key,
                    raw_detected_part_classes=cand.raw_detected_part_classes,
                    side_resolution_method=cand.side_resolution_method,
                    display_part_name=cat_rec.display_part_name,
                    oem_part_number=cat_rec.oem_part_number,
                    part_material=cat_rec.part_material,
                    is_repairable=cat_rec.is_repairable,
                    is_safety_critical=cat_rec.is_safety_critical,
                    detected_damage_classes=cand.detected_damage_classes,
                    primary_damage_class=cand.primary_damage_class,
                    final_iop_ratio=cand.final_iop_ratio,
                    iop_percentage=round(cand.final_iop_ratio * 100.0, 2),
                    iop_estimation_method=cand.iop_estimation_method,
                    zoom_clipped_frames_filtered=cand.zoom_clipped_frames_filtered,
                    persistence_frame_count=cand.persistence_frame_count,
                    part_confidence=cand.part_confidence,
                    damage_confidence=cand.damage_confidence,
                    area_measurement_keyframe=area_hit.keyframe_key,
                    vlm_closeup_keyframe=vlm_hit.keyframe_key,
                    som_annotated_crop_path=som_path,
                    som_raw_crop_path=raw_path,
                    svg_overlay=svg_overlay,
                    catalogue_record=cat_rec,
                )
            )

        return grounded_parts

    @staticmethod
    def _atomic_imwrite(target_path: Path, img_bgr: np.ndarray) -> None:
        tmp_path = target_path.with_suffix(".tmp.jpg")
        cv2.imwrite(str(tmp_path), img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
        os.replace(tmp_path, target_path)
