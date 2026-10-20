from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, Tuple
from uuid import UUID
import numpy as np

if TYPE_CHECKING:
    from app.domain.claim_intent.schemas import ClaimIntent

from app.domain.dual_mask_segmentation.schemas import (
    DiscardedSpilloverHit,
    FrameDualPredictions,
    GroundedDamagedPart,
    GroundingCheckResult,
    GroupedPartCandidate,
    OEMPartCatalogueRecord,
    PartDamageIntersection,
)


class IDualModelInferencer(Protocol):
    """Protocol for batched FP16 execution of Carparts-Seg and CarDD-Seg."""
    def infer_keyframes(
        self, keyframe_paths: Dict[str, Path]
    ) -> Tuple[List[FrameDualPredictions], Dict[str, np.ndarray]]: ...


class IPolygonIntersectionEngine(Protocol):
    """Protocol for Shapely GEOS polygon intersection, spillover, and completeness math."""
    def compute_intersections(
        self,
        frame_predictions: List[FrameDualPredictions],
        claim_intent: Optional["ClaimIntent"] = None,
    ) -> Tuple[List[PartDamageIntersection], List[DiscardedSpilloverHit], Dict[Tuple[str, str], float]]: ...


class IPartSideResolverAndGrouper(Protocol):
    """Protocol for trajectory side resolution and dual-keyframe selection."""
    def resolve_and_group(
        self,
        intersections: List[PartDamageIntersection],
        predictions: List[FrameDualPredictions],
        unclipped_part_areas: Dict[Tuple[str, str], float],
        claim_intent: Optional["ClaimIntent"] = None,
    ) -> List[GroupedPartCandidate]: ...


class ICatalogAndLedgerGrounder(Protocol):
    """Protocol for async PostgreSQL OEM catalogue lookup and guardrail evaluation."""
    async def ground_and_check_guardrails(
        self, policy_id: str, candidates: List[GroupedPartCandidate]
    ) -> GroundingCheckResult: ...


class ISoMCropRenderer(Protocol):
    """Protocol for rendering 15px-dilated SoM crops and normalized SVG overlays."""
    def render_artifacts(
        self,
        claim_id: UUID,
        candidates_with_cat: List[Tuple[GroupedPartCandidate, OEMPartCatalogueRecord]],
        loaded_frames_bgr: Dict[str, np.ndarray],
    ) -> List[GroundedDamagedPart]: ...
