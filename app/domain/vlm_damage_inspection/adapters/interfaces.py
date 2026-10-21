"""Abstract interfaces and protocol definitions for Vision-Language Model adapters."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.vlm_damage_inspection.schemas import InspectionContext, VLMInspectionOutput


@runtime_checkable
class IVLMInspectionAdapter(Protocol):
    """Protocol governing all Vision-Language Model inspection backends."""

    async def inspect_damage(
        self,
        som_crop_bytes: bytes,
        raw_crop_bytes: bytes,
        context: InspectionContext,
    ) -> VLMInspectionOutput:
        """Inspect dual-crop visual evidence and return structured forensic reality."""
        ...

    async def health_check(self) -> bool:
        """Verify reachability and readiness of the vision backend."""
        ...
