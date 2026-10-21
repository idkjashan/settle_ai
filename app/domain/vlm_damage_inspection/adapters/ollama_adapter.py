"""Local Ollama Vision Adapter running miniCPM-V:8b with zero-subshell WSL2 discovery."""

from __future__ import annotations

import base64
import logging
from typing import Optional

import httpx

from app.domain.vlm_damage_inspection.adapters.interfaces import IVLMInspectionAdapter
from app.domain.vlm_damage_inspection.exceptions import Stage3ProviderUnreachableError
from app.domain.vlm_damage_inspection.network_utils import resolve_ollama_url
from app.domain.vlm_damage_inspection.prompts import SYSTEM_PROMPT, build_user_prompt
from app.domain.vlm_damage_inspection.resilient_parser import ResilientJSONParser
from app.domain.vlm_damage_inspection.schemas import (
    InspectionContext,
    VLMInspectionOutput,
)

logger = logging.getLogger(__name__)


class OllamaVisionAdapter(IVLMInspectionAdapter):
    """Adapter connecting to a local or host-level Ollama server (e.g. minicpm-v:8b)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: str = "minicpm-v:8b",
        timeout: float = 12.0,
    ):
        configured_url = base_url or "http://localhost:11434"
        self.base_url = resolve_ollama_url(configured_url).rstrip("/")
        self.model_name = model_name
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=3.0),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._client

    async def inspect_damage(
        self,
        som_crop_bytes: bytes,
        raw_crop_bytes: bytes,
        context: InspectionContext,
    ) -> VLMInspectionOutput:
        """Send dual crops and prompt to Ollama /api/chat with constrained JSON grammar."""
        client = self._get_client()

        b64_som = base64.b64encode(som_crop_bytes).decode("utf-8")
        b64_raw = base64.b64encode(raw_crop_bytes).decode("utf-8")
        user_prompt = build_user_prompt(context)

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": user_prompt,
                    "images": [b64_som, b64_raw],
                },
            ],
            "format": VLMInspectionOutput.model_json_schema(),
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 512,
            },
        }

        url = f"{self.base_url}/api/chat"
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.ConnectError as err:
            logger.error("Failed to connect to Ollama endpoint at %s: %s", url, err)
            raise Stage3ProviderUnreachableError(
                f"Ollama endpoint unreachable at {self.base_url}: {err}",
                provider="ollama",
            ) from err
        except httpx.TimeoutException as err:
            logger.error("Ollama request timed out at %s after %.1fs", url, self.timeout)
            raise Stage3ProviderUnreachableError(
                f"Ollama request timed out after {self.timeout}s: {err}",
                provider="ollama",
            ) from err
        except httpx.HTTPError as err:
            logger.error("HTTP error from Ollama endpoint: %s", err)
            raise Stage3ProviderUnreachableError(
                f"Ollama HTTP error: {err}",
                provider="ollama",
            ) from err

        raw_output = data.get("message", {}).get("content", "") or data.get("response", "")
        return ResilientJSONParser.parse_and_validate(raw_output, VLMInspectionOutput)

    async def health_check(self) -> bool:
        """Check if Ollama server is responsive and model is available."""
        client = self._get_client()
        try:
            resp = await client.get(f"{self.base_url}/api/tags", timeout=2.0)
            if resp.status_code != 200:
                return False
            data = resp.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            # Check if requested model (or model tag) is listed
            if self.model_name in models or any(m.startswith(self.model_name.split(":")[0]) for m in models):
                return True
            logger.warning("Ollama is up at %s, but %s not in %s", self.base_url, self.model_name, models)
            return True  # Server is up
        except Exception as exc:
            logger.debug("Ollama health check failed at %s: %s", self.base_url, exc)
            return False

    async def aclose(self) -> None:
        """Close HTTP connection pool."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
