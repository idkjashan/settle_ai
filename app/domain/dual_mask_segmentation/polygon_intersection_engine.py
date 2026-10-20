from typing import Dict, List, Optional, Tuple
import numpy as np
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.schemas import (
    DiscardedSpilloverHit,
    FrameDualPredictions,
    PartDamageIntersection,
    RawMaskPrediction,
)
from app.domain.dual_mask_segmentation.taxonomy import (
    IGNORED_PART_CLASSES,
    LINEAR_DAMAGE_CLASSES,
    select_primary_damage_class,
)


class PolygonIntersectionEngine:
    """Executes GEOS C++ spatial polygon math, border-margin completeness checks,
    10% boundary spillover filtering, and intra-part damage unary_union.
    """

    def __init__(self, settings: Optional[Stage2Settings] = None):
        self.settings = settings or Stage2Settings()

    @staticmethod
    def sanitize_polygon(pts_xy: np.ndarray, min_area_px: float) -> Optional[BaseGeometry]:
        """Builds a valid Shapely geometry, healing self-intersections via .buffer(0)."""
        if pts_xy is None or len(pts_xy) < 3:
            return None
        try:
            poly = Polygon(pts_xy)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty or poly.area < min_area_px:
                return None
            return poly
        except Exception:
            return None

    def check_panel_completeness(
        self, poly: BaseGeometry, pts_xy: np.ndarray, width_px: int, height_px: int
    ) -> Tuple[bool, float]:
        """Checks whether a segmented vehicle part fits completely inside the camera frame
        without border truncation (defeating the Close-Up Zoom Inflation Attack).
        """
        margin = self.settings.panel_border_margin_px
        xmin, ymin, xmax, ymax = poly.bounds

        bbox_inside = (
            xmin >= margin
            and ymin >= margin
            and xmax <= (width_px - margin)
            and ymax <= (height_px - margin)
        )

        if len(pts_xy) == 0:
            return False, 1.0
        border_hits = np.sum(
            (pts_xy[:, 0] < margin)
            | (pts_xy[:, 1] < margin)
            | (pts_xy[:, 0] > (width_px - margin))
            | (pts_xy[:, 1] > (height_px - margin))
        )
        contact_ratio = float(border_hits) / float(len(pts_xy))
        is_complete = bool(bbox_inside and contact_ratio <= self.settings.max_border_vertex_contact_ratio)
        return is_complete, round(contact_ratio, 4)

    @staticmethod
    def _bboxes_overlap(b1: Tuple[int, int, int, int], b2: Tuple[int, int, int, int]) -> bool:
        return not (b1[2] < b2[0] or b1[0] > b2[2] or b1[3] < b2[1] or b1[1] > b2[3])

    def compute_intersections(
        self, frame_predictions: List[FrameDualPredictions]
    ) -> Tuple[List[PartDamageIntersection], List[DiscardedSpilloverHit], Dict[Tuple[str, str], float]]:
        valid_intersections: List[PartDamageIntersection] = []
        discarded_hits: List[DiscardedSpilloverHit] = []
        unclipped_part_areas: Dict[Tuple[str, str], float] = {}

        for frame_pred in frame_predictions:
            # 1. Build sanitized part polygons
            valid_parts: List[Tuple[RawMaskPrediction, BaseGeometry, bool, float]] = []
            for p_raw in frame_pred.part_predictions:
                if p_raw.class_name in IGNORED_PART_CLASSES or p_raw.confidence < self.settings.part_min_confidence:
                    continue
                p_poly = self.sanitize_polygon(p_raw.polygon_xy_px, self.settings.min_polygon_area_px)
                if p_poly is None:
                    continue
                is_complete, contact_ratio = self.check_panel_completeness(
                    p_poly, p_raw.polygon_xy_px, frame_pred.width_px, frame_pred.height_px
                )
                if is_complete:
                    key = (frame_pred.keyframe_key, p_raw.class_name)
                    unclipped_part_areas[key] = max(unclipped_part_areas.get(key, 0.0), float(p_poly.area))
                valid_parts.append((p_raw, p_poly, is_complete, contact_ratio))

            # 2. Build sanitized damage polygons
            valid_damages: List[Tuple[RawMaskPrediction, BaseGeometry]] = []
            for d_raw in frame_pred.damage_predictions:
                if d_raw.confidence < self.settings.damage_min_confidence_global:
                    continue
                d_poly = self.sanitize_polygon(d_raw.polygon_xy_px, self.settings.min_polygon_area_px)
                if d_poly is not None:
                    valid_damages.append((d_raw, d_poly))

            if not valid_parts or not valid_damages:
                continue

            # 3. Evaluate pairwise overlaps per host part
            for p_raw, p_poly, is_complete, contact_ratio in valid_parts:
                part_area = float(p_poly.area)
                accepted_damage_polys: List[BaseGeometry] = []
                accepted_damage_classes: List[str] = []
                max_d_conf = 0.0

                for d_raw, d_poly in valid_damages:
                    if not self._bboxes_overlap(p_raw.bbox_xyxy, d_raw.bbox_xyxy):
                        continue
                    inter_poly = d_poly.intersection(p_poly)
                    if inter_poly.is_empty:
                        continue
                    inter_area = float(inter_poly.area)
                    dmg_area = float(d_poly.area)
                    if dmg_area <= 0.0 or inter_area < self.settings.min_intersection_area_px:
                        continue

                    spillover_ratio = inter_area / dmg_area
                    if (
                        spillover_ratio < self.settings.spillover_min_ratio
                        and inter_area < self.settings.spillover_override_area_px
                    ):
                        discarded_hits.append(
                            DiscardedSpilloverHit(
                                keyframe_key=frame_pred.keyframe_key,
                                part_class=p_raw.class_name,
                                damage_class=d_raw.class_name,
                                spillover_ratio=round(spillover_ratio, 4),
                                reason="SPILLOVER_BELOW_10_PERCENT",
                            )
                        )
                        continue

                    pair_iop = inter_area / part_area
                    min_iop = (
                        self.settings.iop_floor_linear
                        if d_raw.class_name in LINEAR_DAMAGE_CLASSES
                        else self.settings.iop_floor_areal
                    )
                    if pair_iop < min_iop:
                        continue

                    accepted_damage_polys.append(inter_poly)
                    if d_raw.class_name not in accepted_damage_classes:
                        accepted_damage_classes.append(d_raw.class_name)
                    max_d_conf = max(max_d_conf, d_raw.confidence)

                if not accepted_damage_polys:
                    continue

                # 4. Intra-Part Geometric unary_union (Prevents Dent + Scratch Double Counting)
                union_dmg_poly = unary_union(accepted_damage_polys)
                if not union_dmg_poly.is_valid:
                    union_dmg_poly = union_dmg_poly.buffer(0)
                union_inter_area = float(union_dmg_poly.area)
                union_iop = min(1.0, union_inter_area / part_area)

                valid_intersections.append(
                    PartDamageIntersection(
                        keyframe_key=frame_pred.keyframe_key,
                        frame_index=frame_pred.frame_index,
                        width_px=frame_pred.width_px,
                        height_px=frame_pred.height_px,
                        laplacian_sharpness=frame_pred.laplacian_sharpness,
                        raw_part_class=p_raw.class_name,
                        resolved_part_key=p_raw.class_name,
                        part_confidence=p_raw.confidence,
                        part_bbox_xyxy=p_raw.bbox_xyxy,
                        is_complete_panel=is_complete,
                        border_contact_ratio=contact_ratio,
                        part_area_px=round(part_area, 2),
                        union_damage_intersection_area_px=round(union_inter_area, 2),
                        raw_iop_ratio=round(union_iop, 4),
                        damage_classes=accepted_damage_classes,
                        primary_damage_class=select_primary_damage_class(accepted_damage_classes),
                        max_damage_confidence=round(max_d_conf, 4),
                        part_polygon=p_poly,
                        union_damage_polygon=union_dmg_poly,
                    )
                )

        return valid_intersections, discarded_hits, unclipped_part_areas
