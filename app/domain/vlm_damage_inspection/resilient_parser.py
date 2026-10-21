"""Resilient JSON parsing, markdown codefence extraction, and Pydantic validation."""

from __future__ import annotations

import json
import logging
import re
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.domain.vlm_damage_inspection.exceptions import Stage3MalformedOutputError
from app.domain.vlm_damage_inspection.schemas import VLMInspectionOutput

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class ResilientJSONParser:
    """Robust parser that extracts, repairs, and validates JSON payloads from VLM text responses."""

    @staticmethod
    def clean_json_string(raw_str: str) -> str:
        """Strip markdown fences, leading/trailing conversational text, and trailing commas."""
        cleaned = raw_str.strip()

        # 1. Extract content from code fences if present
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        else:
            # 2. Find outermost JSON object bounds if raw text surrounds the JSON
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                cleaned = cleaned[start : end + 1]

        # 3. Remove trailing commas before closing braces/brackets while preserving whitespace
        cleaned = re.sub(r",(\s*[\]}])", r"\1", cleaned)
        return cleaned

    @classmethod
    def parse_and_validate(
        cls,
        raw_output: str,
        model_cls: Type[T] = VLMInspectionOutput,  # type: ignore[assignment]
    ) -> T:
        """Parse raw VLM string and validate against target Pydantic schema."""
        if not raw_output or not raw_output.strip():
            raise Stage3MalformedOutputError(
                f"VLM output is empty; cannot validate against {model_cls.__name__}."
            )

        cleaned_json = cls.clean_json_string(raw_output)

        try:
            payload_dict = json.loads(cleaned_json)
        except json.JSONDecodeError as json_err:
            # Fallback attempt: normalize common Python dict literals to JSON (True -> true, None -> null)
            try:
                repaired = re.sub(r"\bTrue\b", "true", cleaned_json)
                repaired = re.sub(r"\bFalse\b", "false", repaired)
                repaired = re.sub(r"\bNone\b", "null", repaired)
                repaired = re.sub(r",(\s*[\]}])", r"\1", repaired)
                payload_dict = json.loads(repaired)
            except Exception:
                logger.error("JSON decode failure on VLM output: %r", raw_output[:300])
                raise Stage3MalformedOutputError(
                    f"Failed to decode JSON from VLM output: {json_err}",
                    raw_output=raw_output,
                ) from json_err

        # Resilient repair: if confidence is expressed on 0-100 scale (e.g. 95 or 95.0), normalize to [0.0, 1.0]
        if isinstance(payload_dict, dict) and "confidence" in payload_dict:
            try:
                conf = float(payload_dict["confidence"])
                if 1.0 < conf <= 100.0:
                    payload_dict["confidence"] = round(conf / 100.0, 4)
            except (ValueError, TypeError):
                pass

        try:
            return model_cls.model_validate(payload_dict)
        except ValidationError as val_err:
            logger.error("Schema validation failure against %s: %s", model_cls.__name__, val_err)
            raise Stage3MalformedOutputError(
                f"Validation error against {model_cls.__name__}: {val_err}",
                raw_output=raw_output,
            ) from val_err
