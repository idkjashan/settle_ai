from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
import numpy as np
from shapely.geometry.base import BaseGeometry


class Stage2FailureCode(str, Enum):
    S2_UNREPAIRED_REPEAT_CLAIM = "S2_UNREPAIRED_REPEAT_CLAIM"
    S2_OPPOSITE_SIDE_MULTI_HIT = "S2_OPPOSITE_SIDE_MULTI_HIT"
    S2_SAFETY_CRITICAL_PART_DAMAGED = "S2_SAFETY_CRITICAL_PART_DAMAGED"
    S2_NO_DAMAGE_DETECTED = "S2_NO_DAMAGE_DETECTED"
    S2_LOW_SEGMENTATION_CONFIDENCE = "S2_LOW_SEGMENTATION_CONFIDENCE"
    S2_OEM_CATALOGUE_PART_MISSING = "S2_OEM_CATALOGUE_PART_MISSING"
    S2_MODEL_COMPATIBILITY_ERROR = "S2_MODEL_COMPATIBILITY_ERROR"
    S2_CLAIMED_DAMAGE_NOT_FOUND = "S2_CLAIMED_DAMAGE_NOT_FOUND"
    ESC_07_CLAIMED_DAMAGE_NOT_FOUND = "ESC-07_CLAIMED_DAMAGE_NOT_FOUND"


@dataclass(frozen=True)
class RawMaskPrediction:
    class_id: int
    class_name: str
    confidence: float
    bbox_xyxy: Tuple[int, int, int, int]
    polygon_xy_px: np.ndarray


@dataclass
class FrameDualPredictions:
    keyframe_key: str
    frame_path: Path
    frame_index: int
    width_px: int
    height_px: int
    laplacian_sharpness: float
    part_predictions: List[RawMaskPrediction] = field(default_factory=list)
    damage_predictions: List[RawMaskPrediction] = field(default_factory=list)


@dataclass
class PartDamageIntersection:
    keyframe_key: str
    frame_index: int
    width_px: int
    height_px: int
    laplacian_sharpness: float
    raw_part_class: str
    resolved_part_key: str
    part_confidence: float
    part_bbox_xyxy: Tuple[int, int, int, int]
    is_complete_panel: bool
    border_contact_ratio: float
    part_area_px: float
    union_damage_intersection_area_px: float
    raw_iop_ratio: float
    damage_classes: List[str]
    primary_damage_class: str
    max_damage_confidence: float
    part_polygon: BaseGeometry
    union_damage_polygon: BaseGeometry
    is_claimed: bool = True
    claim_status: str = "CLAIMED"


@dataclass
class DiscardedSpilloverHit:
    keyframe_key: str
    part_class: str
    damage_class: str
    spillover_ratio: float
    reason: str


@dataclass
class GroupedPartCandidate:
    canonical_part_key: str
    raw_detected_part_classes: List[str]
    side_resolution_method: str
    detected_damage_classes: List[str]
    primary_damage_class: str
    final_iop_ratio: float
    iop_estimation_method: str
    zoom_clipped_frames_filtered: int
    persistence_frame_count: int
    part_confidence: float
    damage_confidence: float
    area_measurement_intersection: PartDamageIntersection
    vlm_closeup_intersection: PartDamageIntersection
    is_claimed: bool = True
    claim_status: str = "CLAIMED"


@dataclass(frozen=True)
class OEMPartCatalogueRecord:
    canonical_part_key: str
    display_part_name: str
    oem_part_number: str
    part_material: str
    depreciation_rate_non_zero_dep: float
    oem_part_cost_inr: float
    rr_labour_inr: float
    denting_base_labour_inr: float
    full_panel_paint_inr: float
    pdr_or_polish_flat_inr: float
    is_repairable: bool
    is_safety_critical: bool


@dataclass(frozen=True)
class GroundingCheckResult:
    registration_number: str
    make: str
    model: str
    verified_pairs: List[Tuple[GroupedPartCandidate, OEMPartCatalogueRecord]]


@dataclass(frozen=True)
class SVGOverlayPayload:
    keyframe_key: str
    view_box: str
    part_svg_points_norm: List[Tuple[float, float]]
    damage_svg_points_norm: List[Tuple[float, float]]


@dataclass
class GroundedDamagedPart:
    canonical_part_key: str
    raw_detected_part_classes: List[str]
    side_resolution_method: str
    display_part_name: str
    oem_part_number: str
    part_material: str
    is_repairable: bool
    is_safety_critical: bool
    detected_damage_classes: List[str]
    primary_damage_class: str
    final_iop_ratio: float
    iop_percentage: float
    iop_estimation_method: str
    zoom_clipped_frames_filtered: int
    persistence_frame_count: int
    part_confidence: float
    damage_confidence: float
    area_measurement_keyframe: str
    vlm_closeup_keyframe: str
    som_annotated_crop_path: Path
    som_raw_crop_path: Path
    svg_overlay: SVGOverlayPayload
    catalogue_record: OEMPartCatalogueRecord
    is_claimed: bool = True
    claim_status: str = "CLAIMED"


@dataclass
class Stage3HandoffPayload:
    claim_id: UUID
    policy_id: str
    registration_number: str
    make: str
    model: str
    grounded_parts: List[GroundedDamagedPart]
    telemetry: Dict[str, Any]
    claim_intent: Optional[Any] = None
    unclaimed_preexisting_parts: List[GroupedPartCandidate] = field(default_factory=list)
