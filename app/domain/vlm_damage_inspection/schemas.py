"""Domain schemas and data contracts for Stage 3: Set-of-Marks VLM Damage Inspection.

This module defines the forensic damage taxonomy, 5-grade depth classification matrix,
quarantine data models, inspection output schemas, and downstream Stage 4 handoff contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.dual_mask_segmentation.schemas import (
    GroundedDamagedPart,
    OEMPartCatalogueRecord,
    SVGOverlayPayload,
)


class DepthGrade(str, Enum):
    """5-Grade Depth Classification Matrix ($L_1 \\dots L_5$) determining actuarial repair action."""
    L1_SURFACE_SCUFF = "L1_SURFACE_SCUFF"
    L2_BASECOAT_SCRATCH = "L2_BASECOAT_SCRATCH"
    L3_SHALLOW_DENT_PDR = "L3_SHALLOW_DENT_PDR"
    L4_CREASED_DENT = "L4_CREASED_DENT"
    L5_STRUCTURAL_TEAR = "L5_STRUCTURAL_TEAR"


class VehicleOrientation(str, Enum):
    """Vehicle aspect / viewpoint orientation relative to the camera."""
    FRONT = "FRONT"
    REAR = "REAR"
    LEFT_SIDE = "LEFT_SIDE"
    RIGHT_SIDE = "RIGHT_SIDE"
    FRONT_LEFT_3_QUARTER = "FRONT_LEFT_3_QUARTER"
    FRONT_RIGHT_3_QUARTER = "FRONT_RIGHT_3_QUARTER"
    REAR_LEFT_3_QUARTER = "REAR_LEFT_3_QUARTER"
    REAR_RIGHT_3_QUARTER = "REAR_RIGHT_3_QUARTER"
    ROOF = "ROOF"
    OVERHEAD_ROOF = "OVERHEAD_ROOF"
    UNKNOWN = "UNKNOWN"


class FalsePositiveReason(str, Enum):
    """Taxonomy of non-physical surface contaminants and optical artifacts."""
    NONE = "NONE"
    MUD_OR_DIRT = "MUD_OR_DIRT"
    BIRD_DROPPINGS = "BIRD_DROPPINGS"
    CHALK_OR_MARKER = "CHALK_OR_MARKER"
    DECAL_OR_STICKER = "DECAL_OR_STICKER"
    WATER_DROPLET = "WATER_DROPLET"
    SPECULAR_GLARE = "SPECULAR_GLARE"
    ASPHALT_REFLECTION = "ASPHALT_REFLECTION"
    DUPLICATE_DAMAGE = "DUPLICATE_DAMAGE"
    ORIENTATION_OR_PART_MISMATCH = "ORIENTATION_OR_PART_MISMATCH"
    OTHER_NON_DAMAGE = "OTHER_NON_DAMAGE"


class Stage3FailureCode(str, Enum):
    """Failure, quarantine, and forensic escalation codes for Stage 3."""
    S3_FALSE_POSITIVE_FILTERED = "S3_FALSE_POSITIVE_FILTERED"
    S3_RUST_OR_OXIDATION_DETECTED = "S3_RUST_OR_OXIDATION_DETECTED"
    S3_STRUCTURAL_MISALIGNMENT_DETECTED = "S3_STRUCTURAL_MISALIGNMENT_DETECTED"
    S3_NO_REAL_DAMAGE_DETECTED = "S3_NO_REAL_DAMAGE_DETECTED"
    S3_DUPLICATE_DAMAGE_DISMISSED = "S3_DUPLICATE_DAMAGE_DISMISSED"
    S3_ORIENTATION_MISMATCH_QUARANTINED = "S3_ORIENTATION_MISMATCH_QUARANTINED"
    S3_COMPONENT_MISMATCH_QUARANTINED = "S3_COMPONENT_MISMATCH_QUARANTINED"
    S3_PROVIDER_TIMEOUT = "S3_PROVIDER_TIMEOUT"
    S3_PROVIDER_UNREACHABLE = "S3_PROVIDER_UNREACHABLE"
    S3_MALFORMED_OUTPUT = "S3_MALFORMED_OUTPUT"
    ESC_04_PREEXISTING_CORROSION = "ESC-04_PREEXISTING_CORROSION"
    ESC_06_STRUCTURAL_HAZARD = "ESC-06_STRUCTURAL_HAZARD"
    ESC_07_NO_REAL_DAMAGE_DETECTED = "ESC-07_NO_REAL_DAMAGE_DETECTED"


class VLMProviderType(str, Enum):
    """Supported Vision-Language Model provider backends."""
    OLLAMA = "ollama"
    GEMINI = "gemini"
    OPENAI = "openai"
    MOCK = "mock"
    AUTO = "auto"


class InspectionContext(BaseModel):
    """Contextual metadata injected into the VLM inspection prompt."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    canonical_part_key: str
    part_display_name: str = ""
    primary_damage_class: str
    make: str
    model: str
    iop_ratio: float = 0.0
    is_claimed: bool = True
    claim_id: Optional[str] = None
    som_annotated_crop_path: Optional[Path] = None
    som_raw_crop_path: Optional[Path] = None

    @model_validator(mode="before")
    @classmethod
    def resolve_iop_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "iop_ratio" not in data and "final_iop_ratio" in data:
                data["iop_ratio"] = data["final_iop_ratio"]
            if "part_display_name" not in data and "display_part_name" in data:
                data["part_display_name"] = data["display_part_name"]
        return data

    @property
    def final_iop_ratio(self) -> float:
        return self.iop_ratio


@dataclass(frozen=True)
class InspectionCropPair:
    """In-memory binary image buffers of the dual-crop pair."""
    annotated_som_bytes: bytes
    raw_crop_bytes: bytes
    part_key: str


class VLMInspectionOutput(BaseModel):
    """Constrained Pydantic schema enforcing structured forensic output from VLM backends."""
    is_real_physical_damage: bool = Field(
        ...,
        description="True if real physical damage; False if surface dirt, bird droppings, chalk, decals, water, or glare.",
    )
    false_positive_reason: FalsePositiveReason = Field(
        default=FalsePositiveReason.NONE,
        description="Specific contaminant cause if is_real_physical_damage is False.",
    )
    depth_grade: DepthGrade = Field(
        ...,
        description="Depth severity classification from L1 (buffable scuff) to L5 (structural tear/replacement).",
    )
    has_rust_or_oxidation: bool = Field(
        default=False,
        description="True if reddish-brown iron rust, oxidation, or weathered pre-existing decay is visible inside the damage.",
    )
    rust_details: Optional[str] = Field(
        default=None,
        description="Forensic description of rust/oxidation if detected.",
    )
    has_panel_gap_misalignment: bool = Field(
        default=False,
        description="True if adjacent panel seams are uneven, wedged, or pinched, indicating structural frame shift.",
    )
    misalignment_details: Optional[str] = Field(
        default=None,
        description="Forensic description of panel gap or frame misalignment if detected.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence score in the forensic determination.",
    )
    visual_reasoning_short: str = Field(
        ...,
        max_length=512,
        description="One concise sentence explaining the physical and tactile visual findings.",
    )
    vehicle_orientation: VehicleOrientation = Field(
        default=VehicleOrientation.UNKNOWN,
        description="Observed orientation / perspective of the vehicle in the crop (FRONT, REAR, LEFT_SIDE, RIGHT_SIDE, etc.).",
    )
    detected_component: Optional[str] = Field(
        default=None,
        description="Physical component observed under inspection (e.g. front_bumper, front_left_door).",
    )
    component_matches_target: bool = Field(
        default=True,
        description="True if the visual evidence matches the target component; False if misidentified or adjacent.",
    )
    possible_duplicate: bool = Field(
        default=False,
        description="True if this damage appears identical or duplicate with an adjacent/previously inspected component.",
    )
    duplicate_of_part_key: Optional[str] = Field(
        default=None,
        description="Canonical key of the part this damage is suspected of duplicating, if applicable.",
    )
    missing_parts_detected: List[str] = Field(
        default_factory=list,
        description="Adjacent or visible components in the crop with ungrounded damage left out of inspection.",
    )
    needs_reidentification: bool = Field(
        default=False,
        description="True if the image or sub-crop needs to be routed back to the identification model for re-verification.",
    )
    reidentification_roi_bbox: Optional[List[int]] = Field(
        default=None,
        description="Optional bounding box [x1, y1, x2, y2] within crop for targeted re-identification.",
    )


@dataclass
class VerifiedDamagedPart:
    """Ground-truth verified damaged part enriched with VLM forensic depth severity."""
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
    depth_grade: DepthGrade
    vlm_confidence: float
    visual_reasoning_short: str
    raw_vlm_output: Optional[VLMInspectionOutput] = None
    svg_overlay: Optional[SVGOverlayPayload] = None
    catalogue_record: Optional[OEMPartCatalogueRecord] = None
    is_claimed: bool = True
    claim_status: str = "CLAIMED"
    latency_ms: float = 0.0
    vehicle_orientation: VehicleOrientation = VehicleOrientation.UNKNOWN
    detected_component: Optional[str] = None
    component_matches_target: bool = True
    possible_duplicate: bool = False
    missing_parts_detected: List[str] = field(default_factory=list)
    reidentified_by_model: bool = False

    @property
    def is_real_physical_damage(self) -> bool:
        """Physical reality flag; True for all verified damaged parts."""
        if self.raw_vlm_output is not None:
            return self.raw_vlm_output.is_real_physical_damage
        return True

    @classmethod
    def from_grounded_part(
        cls,
        grounded_part: GroundedDamagedPart,
        vlm_output: VLMInspectionOutput,
        latency_ms: float = 0.0,
    ) -> "VerifiedDamagedPart":
        """Instantiate VerifiedDamagedPart from upstream GroundedDamagedPart and VLMInspectionOutput."""
        return cls(
            canonical_part_key=grounded_part.canonical_part_key,
            raw_detected_part_classes=list(grounded_part.raw_detected_part_classes),
            side_resolution_method=grounded_part.side_resolution_method,
            display_part_name=grounded_part.display_part_name,
            oem_part_number=grounded_part.oem_part_number,
            part_material=grounded_part.part_material,
            is_repairable=grounded_part.is_repairable,
            is_safety_critical=grounded_part.is_safety_critical,
            detected_damage_classes=list(grounded_part.detected_damage_classes),
            primary_damage_class=grounded_part.primary_damage_class,
            final_iop_ratio=grounded_part.final_iop_ratio,
            iop_percentage=grounded_part.iop_percentage,
            iop_estimation_method=grounded_part.iop_estimation_method,
            zoom_clipped_frames_filtered=grounded_part.zoom_clipped_frames_filtered,
            persistence_frame_count=grounded_part.persistence_frame_count,
            part_confidence=grounded_part.part_confidence,
            damage_confidence=grounded_part.damage_confidence,
            area_measurement_keyframe=grounded_part.area_measurement_keyframe,
            vlm_closeup_keyframe=grounded_part.vlm_closeup_keyframe,
            som_annotated_crop_path=grounded_part.som_annotated_crop_path,
            som_raw_crop_path=grounded_part.som_raw_crop_path,
            svg_overlay=grounded_part.svg_overlay,
            catalogue_record=grounded_part.catalogue_record,
            is_claimed=grounded_part.is_claimed,
            claim_status=grounded_part.claim_status,
            depth_grade=vlm_output.depth_grade,
            vlm_confidence=vlm_output.confidence,
            visual_reasoning_short=vlm_output.visual_reasoning_short,
            raw_vlm_output=vlm_output,
            latency_ms=latency_ms,
            vehicle_orientation=getattr(vlm_output, "vehicle_orientation", VehicleOrientation.UNKNOWN),
            detected_component=getattr(vlm_output, "detected_component", None),
            component_matches_target=getattr(vlm_output, "component_matches_target", True),
            possible_duplicate=getattr(vlm_output, "possible_duplicate", False),
            missing_parts_detected=list(getattr(vlm_output, "missing_parts_detected", [])),
            reidentified_by_model=False,
        )


@dataclass
class QuarantinedPartRecord:
    """Record of a candidate part classified as a superficial false positive and dropped from billing."""
    canonical_part_key: str
    primary_damage_class: str
    false_positive_reason: FalsePositiveReason
    visual_reasoning_short: str
    vlm_confidence: float
    som_crop_path: Optional[Path] = None
    latency_ms: float = 0.0
    vehicle_orientation: Optional[VehicleOrientation] = None
    is_duplicate: bool = False
    duplicate_of_part: Optional[str] = None


@dataclass
class Stage3Telemetry:
    """Telemetry data captured during Stage 3 execution."""
    provider: str
    total_latency_ms: float
    parts_inspected_count: int
    parts_verified_count: int
    parts_quarantined_count: int
    circuit_breaker_trips: int = 0
    tokens_used: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Stage4HandoffPayload:
    """Downstream contract payload passed from Stage 3 to Stage 4 Actuarial Pricing Engine."""
    claim_id: UUID
    policy_id: str
    registration_number: str
    make: str
    model: str
    verified_parts: List[VerifiedDamagedPart]
    quarantined_parts: List[QuarantinedPartRecord] = field(default_factory=list)
    telemetry: Dict[str, Any] = field(default_factory=dict)
    claim_intent: Optional[Any] = None

    @property
    def dismissed_parts(self) -> List[QuarantinedPartRecord]:
        """Backward-compatible alias for quarantined_parts."""
        return self.quarantined_parts
