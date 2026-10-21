"""Re-export of IVLMInspectionAdapter and InspectionContext for domain root imports."""

from __future__ import annotations

from app.domain.vlm_damage_inspection.adapters.interfaces import IVLMInspectionAdapter
from app.domain.vlm_damage_inspection.schemas import InspectionContext

__all__ = ["IVLMInspectionAdapter", "InspectionContext"]
