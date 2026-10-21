"""Provider adapters and factory exports for Stage 3 VLM Damage Inspection."""

from __future__ import annotations

from app.domain.vlm_damage_inspection.adapters.factory import (
    VLMProviderFactory,
    get_vlm_adapter,
)
from app.domain.vlm_damage_inspection.adapters.gemini_adapter import GeminiVisionAdapter
from app.domain.vlm_damage_inspection.adapters.interfaces import IVLMInspectionAdapter
from app.domain.vlm_damage_inspection.adapters.mock_adapter import DeterministicMockVLMAdapter
from app.domain.vlm_damage_inspection.adapters.ollama_adapter import OllamaVisionAdapter
from app.domain.vlm_damage_inspection.adapters.openai_adapter import OpenAIVisionAdapter

__all__ = [
    "IVLMInspectionAdapter",
    "DeterministicMockVLMAdapter",
    "OllamaVisionAdapter",
    "GeminiVisionAdapter",
    "OpenAIVisionAdapter",
    "get_vlm_adapter",
    "VLMProviderFactory",
]
