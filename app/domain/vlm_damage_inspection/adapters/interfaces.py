"""Abstract interfaces and protocol definitions for Vision-Language Model adapters."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from app.domain.vlm_damage_inspection.schemas import InspectionContext, VLMInspectionOutput


@runtime_checkable
class IVLMInspectionAdapter(Protocol):
    """Protocol governing all Vision-Language Model inspection backends."""

    async def inspect_damage(
        self,
        som_crop_bytes: bytes,
        raw_crop_bytes: bytes,
        context: InspectionContext,
        full_frame_bytes: Optional[bytes] = None,
    ) -> VLMInspectionOutput:
        """Inspect visual evidence (SoM crop, raw crop, and optional full frame) and return structured forensic reality."""
        ...

    async def health_check(self) -> bool:
        """Verify reachability and readiness of the vision backend."""
        ...
