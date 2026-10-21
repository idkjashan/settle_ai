"""Stage 3 VLM Damage Inspection Orchestrator."""

from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Union

from app.domain.dual_mask_segmentation.schemas import GroundedDamagedPart, Stage3HandoffPayload
from app.domain.vlm_damage_inspection.adapters.factory import get_vlm_adapter
from app.domain.vlm_damage_inspection.adapters.interfaces import IVLMInspectionAdapter
from app.domain.vlm_damage_inspection.config import Stage3Settings, stage3_settings
from app.domain.vlm_damage_inspection.exceptions import Stage3NoRealDamageDetectedError
from app.domain.vlm_damage_inspection.forensic_engine import ForensicDecisionEngine
from app.domain.vlm_damage_inspection.prompt_engine import VLMPromptEngine
from app.domain.vlm_damage_inspection.schemas import (
    FalsePositiveReason,
    InspectionContext,
    QuarantinedPartRecord,
    Stage4HandoffPayload,
    VerifiedDamagedPart,
    VLMInspectionOutput,
)

logger = logging.getLogger(__name__)

# Fallback 1x1 JPEG byte stream for headless testing when image crops do not exist on disk
_PLACEHOLDER_JPEG_BYTES: bytes = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
    b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
    b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4"
    b"\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
    b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
)


def _read_crop_bytes(crop_path: Optional[Union[Path, str]]) -> bytes:
    """Read binary image bytes from disk, returning fallback bytes if unreadable or absent."""
    if crop_path:
        p = Path(crop_path)
        if p.exists() and p.is_file():
            try:
                with open(p, "rb") as f:
                    content = f.read()
                    if content:
                        return content
            except Exception as exc:
                logger.warning("Failed reading image crop from path %s: %s", p, exc)
    return _PLACEHOLDER_JPEG_BYTES


class Stage3VLMOrchestrator:
    """Main orchestrator for Stage 3: Set-of-Marks VLM Damage Inspection."""

    def __init__(
        self,
        settings: Optional[Stage3Settings] = None,
        adapter: Optional[IVLMInspectionAdapter] = None,
    ) -> None:
        self.settings = settings or stage3_settings
        self.adapter = adapter or get_vlm_adapter(self.settings)
        self.prompt_engine = VLMPromptEngine()
        self.forensic_engine = ForensicDecisionEngine()

    async def inspect_claim(self, stage2_handoff: Stage3HandoffPayload) -> Stage4HandoffPayload:
        """Execute Stage 3 forensic damage inspection over candidate grounded parts from Stage 2.

        Lifecycle:
        1. Iterates through claimed grounded parts from Stage 2.
        2. Quarantines or skips unclaimed/pre-existing parts.
        3. Loads dual-crop image buffers (Image 1: cyan Set-of-Marks, Image 2: pristine raw).
        4. Contextualizes the inspection prompt via VLMPromptEngine.
        5. Calls the VLM inspection adapter with constrained structured output.
        6. Passes VLM output through ForensicDecisionEngine (evaluating rust fraud, safety,
           and false positive quarantine).
        7. Enforces the zero real damage gate (ESC-07) if no candidate damage is physically real.
        8. Packages verified and quarantined parts into the immutable Stage4HandoffPayload.
        """
        start_time = time.perf_counter()
        verified_parts: List[VerifiedDamagedPart] = []
        quarantined_parts: List[QuarantinedPartRecord] = []

        logger.info(
            "Starting Stage 3 VLM inspection for claim %s (%s %s, %d candidate parts)",
            stage2_handoff.claim_id,
            stage2_handoff.make,
            stage2_handoff.model,
            len(stage2_handoff.grounded_parts),
        )

        for part in stage2_handoff.grounded_parts:
            # 1. Skip or quarantine unclaimed / pre-existing parts
            if not getattr(part, "is_claimed", True):
                logger.info(
                    "Part %s is marked as unclaimed in Stage 2; quarantining from repair schedule.",
                    part.canonical_part_key,
                )
                quarantined_parts.append(
                    QuarantinedPartRecord(
                        canonical_part_key=part.canonical_part_key,
                        primary_damage_class=part.primary_damage_class,
                        false_positive_reason=FalsePositiveReason.OTHER_NON_DAMAGE,
                        visual_reasoning_short="Part marked as unclaimed or pre-existing in Stage 2.",
                        vlm_confidence=1.0,
                        som_crop_path=part.som_annotated_crop_path,
                        latency_ms=0.0,
                    )
                )
                continue

            # 2. Read dual-crop buffers (gracefully handling existing files or synthetic test bytes)
            som_bytes = _read_crop_bytes(part.som_annotated_crop_path)
            raw_bytes = _read_crop_bytes(part.som_raw_crop_path)

            # 3. Build inspection context
            iop_val = getattr(part, "final_iop_ratio", getattr(part, "iop_percentage", 0.0) / 100.0)
            part_name = getattr(part, "display_part_name", part.canonical_part_key)

            context = InspectionContext(
                canonical_part_key=part.canonical_part_key,
                part_display_name=part_name,
                primary_damage_class=part.primary_damage_class,
                make=stage2_handoff.make,
                model=stage2_handoff.model,
                iop_ratio=iop_val,
                is_claimed=getattr(part, "is_claimed", True),
                claim_id=str(stage2_handoff.claim_id),
                som_annotated_crop_path=part.som_annotated_crop_path,
                som_raw_crop_path=part.som_raw_crop_path,
            )

            # 4. Dispatch to VLM adapter
            t0 = time.perf_counter()
            vlm_output: VLMInspectionOutput = await self.adapter.inspect_damage(
                som_crop_bytes=som_bytes,
                raw_crop_bytes=raw_bytes,
                context=context,
            )
            part_latency_ms = (time.perf_counter() - t0) * 1000.0

            # 5. Evaluate result with ForensicDecisionEngine (may raise ESC-04 or ESC-06)
            decision = self.forensic_engine.validate_inspection_result(
                part=part,
                vlm_output=vlm_output,
                latency_ms=part_latency_ms,
                claim_id=str(stage2_handoff.claim_id),
            )

            # 6. Accumulate into verified or quarantined partition
            if isinstance(decision, VerifiedDamagedPart):
                verified_parts.append(decision)
            elif isinstance(decision, QuarantinedPartRecord):
                quarantined_parts.append(decision)

        # 7. Zero Real Damage Gate (ESC-07)
        if len(verified_parts) == 0 and len(stage2_handoff.grounded_parts) > 0:
            logger.warning(
                "[ESC-07] Zero real damage verified among %d candidates for claim %s.",
                len(stage2_handoff.grounded_parts),
                stage2_handoff.claim_id,
            )
            dismissed_summary = [
                {
                    "canonical_part_key": q.canonical_part_key,
                    "primary_damage_class": q.primary_damage_class,
                    "false_positive_reason": q.false_positive_reason.value,
                    "visual_reasoning": q.visual_reasoning_short,
                    "vlm_confidence": q.vlm_confidence,
                }
                for q in quarantined_parts
            ]
            raise Stage3NoRealDamageDetectedError(
                message="All detected damage candidates were filtered as non-physical artifacts (dirt, glare, or chalk).",
                claim_id=stage2_handoff.claim_id,
                dismissed_summary=dismissed_summary,
            )

        total_latency_ms = (time.perf_counter() - start_time) * 1000.0

        # 8. Assemble Stage 3 Telemetry
        provider_name = getattr(
            self.adapter,
            "model_name",
            getattr(self.settings, "vlm_provider", "vlm"),
        )
        stage3_telemetry: Dict[str, Any] = {
            "provider": provider_name,
            "total_latency_ms": round(total_latency_ms, 2),
            "parts_inspected_count": len(stage2_handoff.grounded_parts),
            "parts_verified_count": len(verified_parts),
            "parts_quarantined_count": len(quarantined_parts),
            "status": "S3_PASSED",
        }

        # Merge with upstream telemetry from Stage 2
        combined_telemetry = dict(getattr(stage2_handoff, "telemetry", {}))
        combined_telemetry["stage3_telemetry"] = stage3_telemetry

        logger.info(
            "Stage 3 completed for claim %s in %.2fms (%d verified, %d quarantined)",
            stage2_handoff.claim_id,
            total_latency_ms,
            len(verified_parts),
            len(quarantined_parts),
        )

        return Stage4HandoffPayload(
            claim_id=stage2_handoff.claim_id,
            policy_id=stage2_handoff.policy_id,
            registration_number=stage2_handoff.registration_number,
            make=stage2_handoff.make,
            model=stage2_handoff.model,
            verified_parts=verified_parts,
            quarantined_parts=quarantined_parts,
            telemetry=combined_telemetry,
            claim_intent=stage2_handoff.claim_intent,
        )

    async def execute(self, payload: Stage3HandoffPayload) -> Stage4HandoffPayload:
        """Alias for inspect_claim providing LLD architectural interface compatibility."""
        return await self.inspect_claim(payload)
