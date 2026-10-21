"""Live integration tests for Stage 3 VLM Damage Inspection against local Ollama (miniCPM-V:8b).

Features:
- WSL2 host gateway and localhost auto-discovery.
- Checks endpoint availability at http://172.29.128.1:11434 and http://localhost:11434.
- Checks if model minicpm-v:8b (or equivalent) is pulled.
- Gracefully skips via pytest.skip() if Ollama is offline, ensuring 0 test suite failures.
- Dual-crop synthetic generation with 15px cyan Set-of-Marks bounding contour.
- Validates strict Pydantic v2 JSON schema adherence, latency benchmarking, and DepthGrade.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
import time
from typing import Optional, Tuple

import httpx
import pytest

from app.domain.vlm_damage_inspection import (
    DepthGrade,
    InspectionContext,
    OllamaVisionAdapter,
    Stage3ProviderUnreachableError,
    VLMInspectionOutput,
    resolve_ollama_url,
)

logger = logging.getLogger(__name__)

# Fallback minimal 1x1 white JPEG bytes for headless byte-level transport verification
_MINIMAL_JPEG_BYTES: bytes = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
    b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
    b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4"
    b"\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
    b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
)


def _generate_synthetic_crop_pair() -> Tuple[bytes, bytes]:
    """Generate high-contrast dual crops in-memory (Crop 1 with Cyan SoM contour, Crop 2 raw)."""
    try:
        from PIL import Image, ImageDraw

        # 1. Base Car Panel Surface (Grey/Silver painted sheet metal)
        img_raw = Image.new("RGB", (320, 320), color=(180, 185, 190))
        draw_raw = ImageDraw.Draw(img_raw)
        # Draw a simulated scratch/scuff line cutting through the panel
        draw_raw.line([(80, 140), (240, 180)], fill=(80, 80, 80), width=4)
        draw_raw.line([(82, 142), (238, 178)], fill=(40, 40, 40), width=2)

        # 2. SoM Crop: duplicate raw panel and add 15px cyan Set-of-Marks dilated contour
        img_som = img_raw.copy()
        draw_som = ImageDraw.Draw(img_som)
        # Cyan bounding rectangle representing the 15px dilated damage polygon anchor
        cyan_rgb = (0, 255, 255)
        draw_som.rectangle([60, 120, 260, 200], outline=cyan_rgb, width=4)

        buf_raw = io.BytesIO()
        img_raw.save(buf_raw, format="JPEG", quality=90)

        buf_som = io.BytesIO()
        img_som.save(buf_som, format="JPEG", quality=90)

        return buf_som.getvalue(), buf_raw.getvalue()
    except ImportError:
        logger.warning("Pillow not installed; using fallback byte streams.")
        return _MINIMAL_JPEG_BYTES, _MINIMAL_JPEG_BYTES


async def _discover_live_ollama() -> Optional[Tuple[str, str]]:
    """Scan candidate endpoints for active Ollama server with minicpm-v model pulled.

    Returns:
        Tuple of (reachable_base_url, model_name) or None if unreachable.
    """
    candidate_urls = [
        resolve_ollama_url("http://localhost:11434"),
        "http://172.29.128.1:11434",
        "http://localhost:11434",
        "http://127.0.0.1:11434",
    ]

    seen = set()
    for base in candidate_urls:
        if not base or base in seen:
            continue
        seen.add(base)

        endpoint = base.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{endpoint}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    # Check for minicpm-v or any vision model
                    target_model = "minicpm-v:8b"
                    found_model = next(
                        (m for m in models if "minicpm-v" in m or target_model in m),
                        None,
                    )
                    if found_model:
                        logger.info("Discovered active Ollama at %s with model %s", endpoint, found_model)
                        return endpoint, found_model
                    elif models:
                        # Fallback to whatever model is available if minicpm-v isn't found
                        logger.warning(
                            "Ollama up at %s, but minicpm-v not in %s. Using %s.",
                            endpoint,
                            models,
                            models[0],
                        )
                        return endpoint, models[0]
        except Exception as exc:
            logger.debug("Ollama candidate %s unreachable: %s", endpoint, exc)
            continue

    return None


# ==============================================================================
# Live Ollama Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_live_ollama_inference():
    """Live inference test connecting to local/WSL2 Ollama instance."""
    discovery = await _discover_live_ollama()
    if discovery is None:
        pytest.skip(
            "Ollama server is not reachable on localhost or WSL2 gateway (http://172.29.128.1:11434)."
        )

    base_url, model_name = discovery
    logger.info("Executing live Ollama inference test against %s (model: %s)", base_url, model_name)

    adapter = OllamaVisionAdapter(
        base_url=base_url,
        model_name=model_name,
        timeout=90.0,
    )

    try:
        # 1. Health check
        is_healthy = await adapter.health_check()
        assert is_healthy is True, f"Health check failed for Ollama at {base_url}"

        # 2. Prepare dual crop pair
        som_bytes, raw_bytes = _generate_synthetic_crop_pair()
        assert len(som_bytes) > 0
        assert len(raw_bytes) > 0

        # 3. Context
        context = InspectionContext(
            canonical_part_key="front_bumper",
            part_display_name="Front Bumper Fascia",
            primary_damage_class="scratch",
            make="Hyundai",
            model="Creta",
            iop_ratio=0.082,
            claim_id="live-test-claim-001",
        )

        # 4. Measure inference latency
        t_start = time.perf_counter()
        result: VLMInspectionOutput = await adapter.inspect_damage(
            som_crop_bytes=som_bytes,
            raw_crop_bytes=raw_bytes,
            context=context,
        )
        latency_sec = time.perf_counter() - t_start
        logger.info(
            "Live Ollama inference finished in %.2fs: damage=%s, grade=%s, conf=%.2f",
            latency_sec,
            result.is_real_physical_damage,
            result.depth_grade.value,
            result.confidence,
        )

        # 5. Schema & taxonomy assertions
        assert isinstance(result, VLMInspectionOutput)
        assert isinstance(result.is_real_physical_damage, bool)
        assert isinstance(result.depth_grade, DepthGrade)
        assert isinstance(result.has_rust_or_oxidation, bool)
        assert isinstance(result.has_panel_gap_misalignment, bool)
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.visual_reasoning_short, str)
        assert len(result.visual_reasoning_short.strip()) > 0

    finally:
        await adapter.aclose()


@pytest.mark.asyncio
async def test_live_ollama_unreachable_endpoint_raises_provider_error():
    """Verify that an intentionally unreachable port raises Stage3ProviderUnreachableError."""
    dead_adapter = OllamaVisionAdapter(
        base_url="http://127.0.0.1:59999",  # Random closed port
        model_name="minicpm-v:8b",
        timeout=1.0,
    )

    context = InspectionContext(
        canonical_part_key="bonnet",
        primary_damage_class="scratch",
        make="Tata",
        model="Nexon",
    )

    with pytest.raises(Stage3ProviderUnreachableError) as exc_info:
        await dead_adapter.inspect_damage(_MINIMAL_JPEG_BYTES, _MINIMAL_JPEG_BYTES, context)

    assert exc_info.value.failure_code == "S3_PROVIDER_UNREACHABLE"
    assert "unreachable" in str(exc_info.value).lower()
    await dead_adapter.aclose()

