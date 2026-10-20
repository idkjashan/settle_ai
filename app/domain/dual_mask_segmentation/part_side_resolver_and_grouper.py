from collections import defaultdict
import math
from typing import Dict, List, Optional, Tuple

from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.schemas import (
    FrameDualPredictions,
    GroupedPartCandidate,
    PartDamageIntersection,
)
from app.domain.dual_mask_segmentation.taxonomy import (
    GENERIC_TO_SIDED_PART_MAP,
    LEFT_SIDE_PARTS,
    RIGHT_SIDE_PARTS,
    select_primary_damage_class,
)


class PartSideResolverAndGrouper:
    """Resolves generic Carparts-Seg predictions (e.g. 'front_door' -> 'front_left_door')
    using walkaround trajectory context, enforces multi-frame persistence, and separates
    the unclipped area_measurement_frame from the macro vlm_closeup_frame.
    """

    def __init__(self, settings: Optional[Stage2Settings] = None):
        self.settings = settings or Stage2Settings()

    def _infer_frame_sides(self, predictions: List[FrameDualPredictions]) -> List[Tuple[int, str]]:
        ordered = sorted(predictions, key=lambda x: x.frame_index)
        frame_sides: List[Tuple[int, str]] = []
        for fp in ordered:
            left_score = sum(p.confidence for p in fp.part_predictions if p.class_name in LEFT_SIDE_PARTS)
            right_score = sum(p.confidence for p in fp.part_predictions if p.class_name in RIGHT_SIDE_PARTS)
            if left_score > right_score + 0.15:
                frame_sides.append((fp.frame_index, "LEFT"))
            elif right_score > left_score + 0.15:
                frame_sides.append((fp.frame_index, "RIGHT"))
            else:
                frame_sides.append((fp.frame_index, "UNKNOWN"))
        return frame_sides

    def _resolve_generic_part(
        self, raw_part: str, frame_idx: int, frame_sides: List[Tuple[int, str]]
    ) -> Tuple[str, str]:
        if (raw_part, "LEFT") not in GENERIC_TO_SIDED_PART_MAP:
            return raw_part, "DIRECT_EXPLICIT_CLASS"

        left_votes = 0
        right_votes = 0
        ordered_indices = [idx for idx, _ in frame_sides]
        try:
            pos = ordered_indices.index(frame_idx)
        except ValueError:
            pos = 0

        r = self.settings.trajectory_side_window_radius
        window = frame_sides[max(0, pos - r) : min(len(frame_sides), pos + r + 1)]
        for _, side in window:
            if side == "LEFT":
                left_votes += 1
            elif side == "RIGHT":
                right_votes += 1

        if left_votes == 0 and right_votes == 0:
            left_votes = sum(1 for _, s in frame_sides if s == "LEFT")
            right_votes = sum(1 for _, s in frame_sides if s == "RIGHT")

        if left_votes > right_votes:
            return GENERIC_TO_SIDED_PART_MAP[(raw_part, "LEFT")], "TRAJECTORY_PROPAGATED_LEFT"
        if right_votes > left_votes:
            return GENERIC_TO_SIDED_PART_MAP[(raw_part, "RIGHT")], "TRAJECTORY_PROPAGATED_RIGHT"
        return raw_part, "GENERIC_FALLBACK_KEY"

    def resolve_and_group(
        self,
        intersections: List[PartDamageIntersection],
        predictions: List[FrameDualPredictions],
        unclipped_part_areas: Dict[Tuple[str, str], float],
    ) -> List[GroupedPartCandidate]:
        frame_sides = self._infer_frame_sides(predictions)
        grouped: Dict[str, List[Tuple[PartDamageIntersection, str]]] = defaultdict(list)

        for hit in intersections:
            resolved_key, method = self._resolve_generic_part(hit.raw_part_class, hit.frame_index, frame_sides)
            hit.resolved_part_key = resolved_key
            grouped[resolved_key].append((hit, method))

        candidates: List[GroupedPartCandidate] = []
        for part_key, hits_with_method in grouped.items():
            hits = [h for h, _ in hits_with_method]
            methods = {m for _, m in hits_with_method}
            distinct_frames = {h.keyframe_key for h in hits}
            persistence_count = len(distinct_frames)

            max_p_conf = max(h.part_confidence for h in hits)
            max_d_conf = max(h.max_damage_confidence for h in hits)

            if persistence_count < self.settings.min_persistence_frames:
                if not (
                    max_p_conf >= self.settings.single_frame_override_part_conf
                    and max_d_conf >= self.settings.single_frame_override_damage_conf
                ):
                    continue

            complete_hits = [h for h in hits if h.is_complete_panel]
            clipped_count = len(hits) - len(complete_hits)

            def _score_area_frame(h: PartDamageIntersection) -> float:
                frame_cov = math.sqrt(h.part_area_px / float(max(1, h.width_px * h.height_px)))
                sharp_norm = min(1.0, h.laplacian_sharpness / 250.0)
                return frame_cov * h.part_confidence * h.max_damage_confidence * sharp_norm

            def _score_vlm_frame(h: PartDamageIntersection) -> float:
                dmg_scale = math.sqrt(h.union_damage_intersection_area_px)
                sharp_norm = min(1.0, h.laplacian_sharpness / 200.0)
                return dmg_scale * h.max_damage_confidence * sharp_norm

            vlm_best_hit = max(hits, key=_score_vlm_frame)

            if complete_hits:
                area_best_hit = max(complete_hits, key=_score_area_frame)
                final_iop = area_best_hit.raw_iop_ratio
                iop_method = "UNCLIPPED_COMPLETE_PANEL"
            else:
                area_best_hit = max(hits, key=_score_area_frame)
                ref_areas = [
                    area
                    for (kf, p_cls), area in unclipped_part_areas.items()
                    if p_cls in (part_key, area_best_hit.raw_part_class)
                ]
                if ref_areas:
                    median_ref_area = sorted(ref_areas)[len(ref_areas) // 2]
                    est_iop = area_best_hit.union_damage_intersection_area_px / max(1.0, median_ref_area)
                    final_iop = min(self.settings.clipped_panel_max_iop_cap, round(est_iop, 4))
                    iop_method = "CROSS_FRAME_REFERENCE_NORMALIZED"
                else:
                    final_iop = min(
                        self.settings.clipped_panel_max_iop_cap,
                        round(area_best_hit.raw_iop_ratio * self.settings.clipped_panel_iop_scale_factor, 4),
                    )
                    iop_method = "CLIPPED_PANEL_CLAMPED"

            all_dmg_classes = sorted({c for h in hits for c in h.damage_classes})
            raw_part_classes = sorted({h.raw_part_class for h in hits})
            resolution_str = (
                "DIRECT_AND_TRAJECTORY_CONFIRMED"
                if len(methods) > 1
                else next(iter(methods), "DIRECT_EXPLICIT_CLASS")
            )

            candidates.append(
                GroupedPartCandidate(
                    canonical_part_key=part_key,
                    raw_detected_part_classes=raw_part_classes,
                    side_resolution_method=resolution_str,
                    detected_damage_classes=all_dmg_classes,
                    primary_damage_class=select_primary_damage_class(all_dmg_classes),
                    final_iop_ratio=round(final_iop, 4),
                    iop_estimation_method=iop_method,
                    zoom_clipped_frames_filtered=clipped_count,
                    persistence_frame_count=persistence_count,
                    part_confidence=round(max_p_conf, 4),
                    damage_confidence=round(max_d_conf, 4),
                    area_measurement_intersection=area_best_hit,
                    vlm_closeup_intersection=vlm_best_hit,
                )
            )

        return candidates
