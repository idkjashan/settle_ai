from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field
import uuid
import numpy as np


class Stage1FailureCode(str, Enum):
    S1_CUT_HISTOGRAM_DROP = "S1_CUT_HISTOGRAM_DROP"
    S1_CUT_PYSCENEDETECT_TRIGGER = "S1_CUT_PYSCENEDETECT_TRIGGER"
    S1_CUT_SPATIAL_SSIM_DROP = "S1_CUT_SPATIAL_SSIM_DROP"
    S1_CUT_FREEZE_FRAME_DETECTED = "S1_CUT_FREEZE_FRAME_DETECTED"
    S1_NO_VEHICLE_DETECTED = "S1_NO_VEHICLE_DETECTED"
    S1_PLATE_NOT_FOUND_OR_UNREADABLE = "S1_PLATE_NOT_FOUND_OR_UNREADABLE"
    S1_PLATE_SPOOF_DETECTED = "S1_PLATE_SPOOF_DETECTED"
    S1_PLATE_MISMATCH = "S1_PLATE_MISMATCH"
    S1_COLOR_MISMATCH = "S1_COLOR_MISMATCH"
    S1_TRACK_LOST_EXCEEDED = "S1_TRACK_LOST_EXCEEDED"
    S1_TRACK_ID_SWITCHED = "S1_TRACK_ID_SWITCHED"


class CanonicalPartKey(str, Enum):
    FRONT_BUMPER = "front_bumper"
    REAR_BUMPER = "rear_bumper"
    SIDE_BODY_PANEL = "side_body_panel"
    DAMAGE_CLOSEUP_PRIMARY = "damage_closeup_primary"
    HOOD = "hood"
    TRUNK_LID = "trunk_lid"
    FRONT_LEFT_DOOR = "front_left_door"
    FRONT_RIGHT_DOOR = "front_right_door"


class HSVColorBounds(BaseModel):
    h_min: int = Field(default=0, ge=0, le=180)
    h_max: int = Field(default=180, ge=0, le=180)
    s_min: int = Field(default=0, ge=0, le=255)
    s_max: int = Field(default=255, ge=0, le=255)
    v_min: int = Field(default=0, ge=0, le=255)
    v_max: int = Field(default=255, ge=0, le=255)


@dataclass(frozen=True)
class FastFailHandoffPayload:
    claim_id: uuid.UUID
    scratch_video_path: Path
    policy_id: str
    video_sha256: str
    is_demo_rehearsal: bool = False


class PolicyGroundingContext(BaseModel):
    policy_id: str
    registration_number: str
    make: str
    model: str
    registered_color: str
    registered_color_hsv: Optional[Dict[str, Any]] = None


class CutDetectionResult(BaseModel):
    is_continuous: bool
    evaluated_frames: int = 0
    effective_fps: float = 0.0
    min_global_hsv_corr: float = 1.0
    min_grid_p25_hsv_corr: float = 1.0
    min_triggered_ssim: float = 1.0
    max_pyscenedetect_score: float = 0.0
    max_frozen_frame_run: int = 0
    cut_frame_indices: List[int] = []
    failure_code: Optional[str] = None
    duration_ms: float = 0.0


class PlateValidationResult(BaseModel):
    is_verified: bool
    deferred_to_late_track: bool = False
    expected_plate: str
    extracted_plate: Optional[str] = None
    ocr_confidence: float = 0.0
    homoglyph_edit_cost: float = 0.0
    used_gemini_fallback: bool = False
    is_spatially_grounded_on_vehicle: bool = False
    anchor_frame_idx: int = 0
    anchor_timestamp_sec: float = 0.0
    anchor_vehicle_bbox: Optional[Tuple[int, int, int, int]] = None
    failure_code: Optional[str] = None
    duration_ms: float = 0.0


class ColorValidationResult(BaseModel):
    is_color_match: bool
    expected_color_name: str
    measured_hue_circular_mean: float = 0.0
    measured_sat_median: float = 0.0
    measured_val_median: float = 0.0
    delta_e_hsv: float = 0.0
    valid_paint_pixel_count: int = 0
    failure_code: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class SelectedKeyframeMeta:
    canonical_part_key: str
    file_path: Path
    frame_index: int
    timestamp_sec: float
    laplacian_variance: float
    glare_ratio: float
    composite_quality_score: float


class TrackingAndKeyframeResult(BaseModel):
    is_persistent: bool
    target_track_id: int = 1
    frames_tracked: int = 0
    track_lost_count: int = 0
    closeup_handoff_triggered: bool = False
    saved_keyframes: Dict[str, str] = {}  # e.g., {"front_bumper": "/tmp/...", "damage_closeup_primary": "/tmp/..."}
    curated_keyframes: List[str] = []  # Top-N non-redundant trajectory keyframes for Stage 2
    late_plate_verified: bool = False
    failure_code: Optional[str] = None
    duration_ms: float = 0.0


class VehicleContinuityTelemetryDTO(BaseModel):
    cut_report: CutDetectionResult
    plate_report: PlateValidationResult
    color_report: ColorValidationResult
    tracking_report: TrackingAndKeyframeResult
    total_execution_ms: float = 0.0
    passed: bool = False
    escalation_code: Optional[str] = None


class Stage1HandoffPayload(BaseModel):
    claim_id: uuid.UUID
    policy_id: str
    scratch_video_path: str
    keyframe_paths: Dict[str, str]
    vehicle_telemetry: VehicleContinuityTelemetryDTO


# Section 10.3 Alias
Stage2HandoffPayload = Stage1HandoffPayload
