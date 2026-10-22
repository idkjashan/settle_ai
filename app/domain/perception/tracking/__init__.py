"""
Auto-Settle AI Perception & Tracking Module.
Occlusion-robust, training-free vehicle damage tracking with intermediate backbone
RoIAlign feature re-identification and temporal confirmation gating.
"""

from app.domain.perception.tracking.feature_extractor import C4FeatureExtractor
from app.domain.perception.tracking.reid_gallery import ReidGallery
from app.domain.perception.tracking.temporal_confirmation_gate import TemporalConfirmationGate
from app.domain.perception.tracking.occlusion_reid_tracker import (
    OcclusionReIDTracker,
    TrackedDamage,
    VideoTrackingResult,
)

__all__ = [
    "C4FeatureExtractor",
    "ReidGallery",
    "TemporalConfirmationGate",
    "OcclusionReIDTracker",
    "TrackedDamage",
    "VideoTrackingResult",
]
