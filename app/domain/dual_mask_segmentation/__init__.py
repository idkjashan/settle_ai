"""
app/domain/dual_mask_segmentation
Stage 2: Dual-Mask Part & Damage Segmentation.
"""
from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.exceptions import (
    Stage2Error,
    Stage2LowConfidenceOrNoDamageError,
    Stage2ModelCompatibilityError,
    Stage2OppositeSideMultiHitError,
    Stage2SafetyCriticalError,
    Stage2UnrepairedRepeatError,
)
from app.domain.dual_mask_segmentation.taxonomy import validate_model_taxonomy
from app.domain.dual_mask_segmentation.schemas import (
    DiscardedSpilloverHit,
    FrameDualPredictions,
    GroundedDamagedPart,
    GroundingCheckResult,
    GroupedPartCandidate,
    OEMPartCatalogueRecord,
    PartDamageIntersection,
    RawMaskPrediction,
    Stage2FailureCode,
    Stage3HandoffPayload,
    SVGOverlayPayload,
)
from app.domain.dual_mask_segmentation.orchestrator import DualMaskSegmentationOrchestrator

__all__ = [
    "Stage2Settings",
    "Stage2Error",
    "Stage2ModelCompatibilityError",
    "Stage2LowConfidenceOrNoDamageError",
    "Stage2OppositeSideMultiHitError",
    "Stage2SafetyCriticalError",
    "Stage2UnrepairedRepeatError",
    "validate_model_taxonomy",
    "DiscardedSpilloverHit",
    "FrameDualPredictions",
    "GroundedDamagedPart",
    "GroundingCheckResult",
    "GroupedPartCandidate",
    "OEMPartCatalogueRecord",
    "PartDamageIntersection",
    "RawMaskPrediction",
    "Stage2FailureCode",
    "Stage3HandoffPayload",
    "SVGOverlayPayload",
    "DualMaskSegmentationOrchestrator",
]
