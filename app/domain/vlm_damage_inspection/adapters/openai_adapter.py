"""OpenAI-compatible Vision API adapter (vLLM, OpenRouter, Azure OpenAI)."""

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


class OpenAIVisionAdapter(IVLMInspectionAdapter):
    """Adapter for any OpenAI-compatible vision chat completions endpoint."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
        model_name: str = "gpt-4o-mini",
        timeout: float = 12.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
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
        full_frame_bytes: Optional[bytes] = None,
    ) -> VLMInspectionOutput:
        """Send crops to OpenAI /chat/completions with json_object response format."""
        if not self.api_key:
            raise Stage3ProviderUnreachableError(
                "OpenAI API key is missing or not configured.",
                provider="openai",
            )

        client = self._get_client()

        b64_som = base64.b64encode(som_crop_bytes).decode("utf-8")
        b64_raw = base64.b64encode(raw_crop_bytes).decode("utf-8")
        user_prompt = build_user_prompt(context)

        user_content: List[Dict[str, Any]] = [
            {"type": "text", "text": user_prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64_som}"},
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64_raw}"},
            },
        ]
        if full_frame_bytes:
            b64_full = base64.b64encode(full_frame_bytes).decode("utf-8")
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64_full}"},
            })

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": user_content,
            },
        ]

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"

        try:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except httpx.ConnectError as err:
            logger.error("Failed to connect to OpenAI endpoint at %s: %s", url, err)
            raise Stage3ProviderUnreachableError(
                f"OpenAI endpoint unreachable: {err}",
                provider="openai",
            ) from err
        except httpx.TimeoutException as err:
            logger.error("OpenAI request timed out after %.1fs", self.timeout)
            raise Stage3ProviderUnreachableError(
                f"OpenAI request timed out after {self.timeout}s: {err}",
                provider="openai",
            ) from err
        except httpx.HTTPStatusError as err:
            logger.error("HTTP error %s from OpenAI endpoint: %s", err.response.status_code, err.response.text[:300])
            raise Stage3ProviderUnreachableError(
                f"OpenAI HTTP {err.response.status_code}: {err.response.text[:200]}",
                provider="openai",
            ) from err
        except httpx.HTTPError as err:
            logger.error("General HTTP error from OpenAI endpoint: %s", err)
            raise Stage3ProviderUnreachableError(
                f"OpenAI HTTP connection error: {err}",
                provider="openai",
            ) from err

        try:
            choices = data.get("choices", [])
            if not choices:
                raise ValueError("No choices returned from OpenAI.")
            raw_text = choices[0].get("message", {}).get("content", "")
        except (KeyError, IndexError, ValueError) as parse_err:
            raise Stage3ProviderUnreachableError(
                f"Malformed choice structure from OpenAI: {parse_err}",
                provider="openai",
            ) from parse_err

        return ResilientJSONParser.parse_and_validate(raw_text, VLMInspectionOutput)

    async def health_check(self) -> bool:
        """Check API key and endpoint validity."""
        if not self.api_key:
            return False

        client = self._get_client()
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.base_url}/models"
        try:
            resp = await client.get(url, headers=headers, timeout=3.0)
            return resp.status_code == 200
        except Exception as exc:
            logger.debug("OpenAI health check failed: %s", exc)
            return False

    async def aclose(self) -> None:
        """Close HTTP connection pool."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
