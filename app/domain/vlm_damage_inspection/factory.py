"""Re-export of VLMProviderFactory and get_vlm_adapter at domain root."""

from __future__ import annotations

from app.domain.vlm_damage_inspection.adapters.factory import (
    VLMProviderFactory,
    get_vlm_adapter,
)

__all__ = ["VLMProviderFactory", "get_vlm_adapter"]
