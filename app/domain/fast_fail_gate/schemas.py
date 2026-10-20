from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field
import uuid

class CaptureSource(str, Enum):
    LIVE_WEBRTC = "LIVE_WEBRTC"
    FILE_UPLOAD = "FILE_UPLOAD"

class FastFailFailureCode(str, Enum):
    # Tier-1 Codes
    POLICY_NOT_FOUND = "POLICY_NOT_FOUND"
    POLICY_INACTIVE = "POLICY_INACTIVE"
    POLICY_EXPIRED_OR_NOT_STARTED = "POLICY_EXPIRED_OR_NOT_STARTED"
    ANNUAL_CASH_CLAIM_LIMIT_REACHED = "ANNUAL_CASH_CLAIM_LIMIT_REACHED"
    DUPLICATE_VIDEO_SUBMISSION = "DUPLICATE_VIDEO_SUBMISSION"
    
    # Tier-2A Container Forensics Codes
    CONTAINER_PARSE_FAILED = "CONTAINER_PARSE_FAILED"
    NO_VIDEO_STREAM = "NO_VIDEO_STREAM"
    RESOLUTION_TOO_LOW = "RESOLUTION_TOO_LOW"
    DURATION_TOO_SHORT = "DURATION_TOO_SHORT"
    DURATION_TOO_LONG = "DURATION_TOO_LONG"
    FRAMERATE_TOO_LOW = "FRAMERATE_TOO_LOW"
    METADATA_EDITED_VIDEO = "METADATA_EDITED_VIDEO"
    
    # Tier-2B Visual Quality Codes
    VIDEO_TOO_DARK = "VIDEO_TOO_DARK"
    VIDEO_TOO_BRIGHT = "VIDEO_TOO_BRIGHT"
    VIDEO_TOO_BLURRY = "VIDEO_TOO_BLURRY"

class Tier1GateReport(BaseModel):
    passed: bool
    policy_id: str
    sha256_hex: str
    failure_codes: List[FastFailFailureCode] = Field(default_factory=list)
    policy_status: Optional[str] = None
    cash_claims_ytd: Optional[int] = None
    max_cash_claims_per_year: Optional[int] = None
    duration_ms: float = 0.0

class ContainerGateReport(BaseModel):
    passed: bool
    failure_codes: List[FastFailFailureCode] = Field(default_factory=list)
    format_name: str = ""
    width: int = 0
    height: int = 0
    duration_sec: float = 0.0
    effective_fps: float = 0.0
    codec_name: str = ""
    detected_editor_tag: Optional[str] = None
    duration_source: str = "format"  # 'format' or 'stream' or 'fallback'
    duration_ms: float = 0.0

class SampledFrameMetric(BaseModel):
    sample_index: int
    normalized_pos: float
    frame_number: int
    timestamp_sec: float
    mean_luminance_y: float
    laplacian_variance: float
    is_dark: bool
    is_overexposed: bool
    is_blurry: bool

class VisualGateReport(BaseModel):
    passed: bool
    failure_codes: List[FastFailFailureCode] = Field(default_factory=list)
    sampled_frames: List[SampledFrameMetric] = Field(default_factory=list)
    mean_luminance_aggregate: float = 0.0
    mean_sharpness_aggregate: float = 0.0
    dark_frame_count: int = 0
    bright_frame_count: int = 0
    blurry_frame_count: int = 0
    duration_ms: float = 0.0

class FastFailTelemetryDTO(BaseModel):
    tier1_report: Tier1GateReport
    container_report: Optional[ContainerGateReport] = None
    visual_report: Optional[VisualGateReport] = None
    total_execution_ms: float = 0.0

class RemediationDirective(BaseModel):
    user_title: str
    user_message: str
    action_items: List[str]
    can_retry: bool

class FastFailResponseDTO(BaseModel):
    passed: bool
    claim_id: uuid.UUID
    escalation_code: Optional[str] = None
    failure_codes: List[FastFailFailureCode] = Field(default_factory=list)
    remediation: Optional[RemediationDirective] = None
    sse_stream_url: Optional[str] = None
    telemetry: Optional[FastFailTelemetryDTO] = None

