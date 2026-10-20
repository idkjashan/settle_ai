from pathlib import Path
from typing import Protocol, Optional
import numpy as np
from app.domain.vehicle_identity_continuity.schemas import (
    CutDetectionResult,
    PlateValidationResult,
    ColorValidationResult,
    TrackingAndKeyframeResult,
    PolicyGroundingContext,
)

class ICutDetector(Protocol):
    def evaluate(self, video_path: Path) -> CutDetectionResult:
        ...

class IPlateOCRValidator(Protocol):
    def validate_initial_window(
        self,
        video_path: Path,
        expected_plate: str,
        initial_seconds: float = 3.5,
    ) -> PlateValidationResult:
        ...

class IColorGroundingValidator(Protocol):
    def validate_paint_color(
        self,
        frame_bgr: np.ndarray,
        vehicle_mask: np.ndarray,
        grounding_context: PolicyGroundingContext,
    ) -> ColorValidationResult:
        ...

class IObjectTrackerAndKeyframer(Protocol):
    def track_and_extract_keyframes(
        self,
        video_path: Path,
        claim_id: str,
        grounding_context: PolicyGroundingContext,
        plate_deferred: bool = False,
    ) -> TrackingAndKeyframeResult:
        ...

