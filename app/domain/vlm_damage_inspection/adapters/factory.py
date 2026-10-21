"""Factory and dynamic provider resolution for Vision-Language Model adapters."""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlsplit

from app.domain.vlm_damage_inspection.adapters.gemini_adapter import GeminiVisionAdapter
from app.domain.vlm_damage_inspection.adapters.interfaces import IVLMInspectionAdapter
from app.domain.vlm_damage_inspection.adapters.mock_adapter import DeterministicMockVLMAdapter
from app.domain.vlm_damage_inspection.adapters.ollama_adapter import OllamaVisionAdapter
from app.domain.vlm_damage_inspection.adapters.openai_adapter import OpenAIVisionAdapter
from app.domain.vlm_damage_inspection.config import Stage3Settings, stage3_settings
from app.domain.vlm_damage_inspection.network_utils import is_port_open, resolve_ollama_url

logger = logging.getLogger(__name__)


def get_vlm_adapter(
    settings: Optional[Stage3Settings] = None,
    provider_override: Optional[str] = None,
) -> IVLMInspectionAdapter:
    """Resolve and instantiate the appropriate IVLMInspectionAdapter backend."""
    cfg = settings or stage3_settings
    provider = (provider_override or cfg.vlm_provider).strip().lower()

    if provider == "mock":
        logger.info("Initializing DeterministicMockVLMAdapter for zero-network testing.")
        return DeterministicMockVLMAdapter()

    if provider == "ollama":
        resolved_url = resolve_ollama_url(cfg.ollama_base_url)
        logger.info("Initializing OllamaVisionAdapter (%s) at %s", cfg.ollama_model, resolved_url)
        return OllamaVisionAdapter(
            base_url=resolved_url,
            model_name=cfg.ollama_model,
            timeout=cfg.request_timeout_seconds,
        )

    if provider == "gemini":
        logger.info("Initializing GeminiVisionAdapter (%s)", cfg.gemini_model)
        return GeminiVisionAdapter(
            api_key=cfg.gemini_api_key,
            model_name=cfg.gemini_model,
            api_endpoint=cfg.gemini_api_endpoint,
            timeout=cfg.request_timeout_seconds,
        )

    if provider == "openai":
        logger.info("Initializing OpenAIVisionAdapter (%s) at %s", cfg.openai_model, cfg.openai_base_url)
        return OpenAIVisionAdapter(
            api_key=cfg.openai_api_key,
            base_url=cfg.openai_base_url,
            model_name=cfg.openai_model,
            timeout=cfg.request_timeout_seconds,
        )

    if provider == "auto":
        # 1. Check local / host Ollama reachability
        resolved_ollama = resolve_ollama_url(cfg.ollama_base_url)
        try:
            parsed = urlsplit(resolved_ollama)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 11434
            if is_port_open(host, port, timeout_sec=0.25):
                logger.info("Auto-selected Ollama adapter at %s (%s)", resolved_ollama, cfg.ollama_model)
                return OllamaVisionAdapter(
                    base_url=resolved_ollama,
                    model_name=cfg.ollama_model,
                    timeout=cfg.request_timeout_seconds,
                )
        except Exception as exc:
            logger.debug("Ollama probe encountered error during auto resolution: %s", exc)

        # 2. Check Cloud Gemini API key
        if cfg.gemini_api_key:
            logger.info("Auto-selected Gemini adapter (%s)", cfg.gemini_model)
            return GeminiVisionAdapter(
                api_key=cfg.gemini_api_key,
                model_name=cfg.gemini_model,
                api_endpoint=cfg.gemini_api_endpoint,
                timeout=cfg.request_timeout_seconds,
            )

        # 3. Check OpenAI API key
        if cfg.openai_api_key:
            logger.info("Auto-selected OpenAI adapter (%s)", cfg.openai_model)
            return OpenAIVisionAdapter(
                api_key=cfg.openai_api_key,
                base_url=cfg.openai_base_url,
                model_name=cfg.openai_model,
                timeout=cfg.request_timeout_seconds,
            )

        # 4. Fallback to Deterministic Mock
        logger.warning("No live VLM provider reachable or configured; falling back to DeterministicMockVLMAdapter.")
        return DeterministicMockVLMAdapter()

    raise ValueError(f"Unknown VLM provider '{provider}'. Must be one of: ollama, gemini, openai, mock, auto.")


class VLMProviderFactory:
    """Factory facade matching LLD architectural specification."""

    @classmethod
    def get_adapter(
        cls,
        provider_type: Optional[str] = None,
        settings: Optional[Stage3Settings] = None,
    ) -> IVLMInspectionAdapter:
        return get_vlm_adapter(settings=settings, provider_override=provider_type)

    @classmethod
    def get_default_adapter(cls, settings: Optional[Stage3Settings] = None) -> IVLMInspectionAdapter:
        return get_vlm_adapter(settings=settings)
