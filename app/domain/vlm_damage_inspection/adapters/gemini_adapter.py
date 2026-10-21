"""Google Gemini Vision REST adapter using native responseSchema constrained decoding."""

from __future__ import annotations

import base64
import logging
from typing import Optional

import httpx

from app.domain.vlm_damage_inspection.adapters.interfaces import IVLMInspectionAdapter
from app.domain.vlm_damage_inspection.exceptions import Stage3ProviderUnreachableError
from app.domain.vlm_damage_inspection.prompts import SYSTEM_PROMPT, build_user_prompt
from app.domain.vlm_damage_inspection.resilient_parser import ResilientJSONParser
from app.domain.vlm_damage_inspection.schemas import (
    InspectionContext,
    VLMInspectionOutput,
)

logger = logging.getLogger(__name__)


class GeminiVisionAdapter(IVLMInspectionAdapter):
    """Adapter communicating with Google Gemini 2.5 Flash via asynchronous REST API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
        api_endpoint: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = 8.0,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.api_endpoint = api_endpoint.rstrip("/")
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
        """Send dual crops to Gemini REST generateContent with constrained JSON schema."""
        if not self.api_key:
            raise Stage3ProviderUnreachableError(
                "Gemini API key is missing or not configured.",
                provider="gemini",
            )

        client = self._get_client()

        b64_som = base64.b64encode(som_crop_bytes).decode("utf-8")
        b64_raw = base64.b64encode(raw_crop_bytes).decode("utf-8")
        user_prompt = build_user_prompt(context)

        url = f"{self.api_endpoint}/models/{self.model_name}:generateContent?key={self.api_key}"

        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [
                {
                    "parts": [
                        {"text": user_prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": b64_som}},
                        {"inline_data": {"mime_type": "image/jpeg", "data": b64_raw}},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
                "responseSchema": VLMInspectionOutput.model_json_schema(),
            },
        }

        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.ConnectError as err:
            logger.error("Failed to connect to Gemini endpoint at %s: %s", self.api_endpoint, err)
            raise Stage3ProviderUnreachableError(
                f"Gemini endpoint unreachable: {err}",
                provider="gemini",
            ) from err
        except httpx.TimeoutException as err:
            logger.error("Gemini request timed out after %.1fs", self.timeout)
            raise Stage3ProviderUnreachableError(
                f"Gemini request timed out after {self.timeout}s: {err}",
                provider="gemini",
            ) from err
        except httpx.HTTPStatusError as err:
            logger.error("HTTP error %s from Gemini endpoint: %s", err.response.status_code, err.response.text[:300])
            raise Stage3ProviderUnreachableError(
                f"Gemini HTTP {err.response.status_code}: {err.response.text[:200]}",
                provider="gemini",
            ) from err
        except httpx.HTTPError as err:
            logger.error("General HTTP error from Gemini endpoint: %s", err)
            raise Stage3ProviderUnreachableError(
                f"Gemini HTTP connection error: {err}",
                provider="gemini",
            ) from err

        try:
            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError("No candidates returned in Gemini response.")
            parts = candidates[0].get("content", {}).get("parts", [])
            raw_text = parts[0].get("text", "") if parts else ""
        except (KeyError, IndexError, ValueError) as parse_err:
            raise Stage3ProviderUnreachableError(
                f"Malformed candidate structure from Gemini: {parse_err}",
                provider="gemini",
            ) from parse_err

        return ResilientJSONParser.parse_and_validate(raw_text, VLMInspectionOutput)

    async def health_check(self) -> bool:
        """Verify API key validity and connectivity to Gemini endpoint."""
        if not self.api_key:
            return False

        client = self._get_client()
        url = f"{self.api_endpoint}/models/{self.model_name}?key={self.api_key}"
        try:
            resp = await client.get(url, timeout=3.0)
            return resp.status_code == 200
        except Exception as exc:
            logger.debug("Gemini health check failed: %s", exc)
            return False

    async def aclose(self) -> None:
        """Close HTTP connection pool."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
