"""Operational configuration and environment settings for Stage 3 VLM Damage Inspection."""

from __future__ import annotations

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Stage3Settings(BaseSettings):
    """Runtime configuration for Vision-Language Model adapters and resilience parameters."""
    model_config = SettingsConfigDict(
        env_prefix="STAGE3_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Provider selection: "ollama", "gemini", "openai", "mock", or "auto"
    vlm_provider: str = Field(default="auto")

    # Local Ollama configuration
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="minicpm-v:8b")

    # Google Gemini REST configuration
    gemini_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    gemini_model: str = Field(default="gemini-2.5-flash")
    gemini_api_endpoint: str = Field(default="https://generativelanguage.googleapis.com/v1beta")

    # OpenAI-compatible Vision API configuration
    openai_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    openai_model: str = Field(default="gpt-4o-mini")

    # Network timeouts & retry policies
    request_timeout_seconds: float = Field(default=12.0)
    max_retries: int = Field(default=2)

    # Circuit breaker thresholds
    circuit_breaker_failure_threshold: int = Field(default=5)
    circuit_breaker_recovery_timeout_seconds: float = Field(default=30.0)


stage3_settings = Stage3Settings()
