"""Stage 3 VLM Damage Inspection Orchestrator."""

from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Sequence, Union

from app.domain.dual_mask_segmentation.schemas import GroundedDamagedPart, Stage3HandoffPayload
from app.domain.vlm_damage_inspection.adapters.factory import get_vlm_adapter
from app.domain.vlm_damage_inspection.adapters.interfaces import IVLMInspectionAdapter
from app.domain.vlm_damage_inspection.config import Stage3Settings, stage3_settings
from app.domain.vlm_damage_inspection.exceptions import Stage3NoRealDamageDetectedError
from app.domain.vlm_damage_inspection.forensic_engine import ForensicDecisionEngine
from app.domain.vlm_damage_inspection.prompt_engine import VLMPromptEngine
from app.domain.vlm_damage_inspection.schemas import (
    FalsePositiveReason,
    HarnessAction,
    InspectionContext,
    QuarantinedPartRecord,
    Stage4HandoffPayload,
    VehicleOrientation,
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


def _cut_roi_bytes(
    image_bytes: bytes,
    roi_bbox: Optional[Union[Sequence[float], Sequence[int]]],
) -> bytes:
    """Extract and return a sub-crop region from image bytes based on normalized or pixel bbox."""
    if not image_bytes or not roi_bbox or len(roi_bbox) != 4:
        return image_bytes
    try:
        import cv2
        import numpy as np

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return image_bytes

        h, w = img.shape[:2]
        c1, c2, c3, c4 = roi_bbox

        if max(c1, c2, c3, c4) <= 1.0:
            # Normalized [ymin, xmin, ymax, xmax] or [x1, y1, x2, y2]
            # Standard order [ymin, xmin, ymax, xmax]
            ymin = max(0, int(c1 * h))
            xmin = max(0, int(c2 * w))
            ymax = min(h, int(c3 * h))
            xmax = min(w, int(c4 * w))
        else:
            # Pixel coordinates [x1, y1, x2, y2]
            xmin = max(0, int(c1))
            ymin = max(0, int(c2))
            xmax = min(w, int(c3))
            ymax = min(h, int(c4))

        if xmax > xmin and ymax > ymin:
            cut = img[ymin:ymax, xmin:xmax]
            success, enc = cv2.imencode(".jpg", cut)
            if success:
                return enc.tobytes()
    except Exception as exc:
        logger.warning("Failed slicing sub-crop ROI: %s", exc)
    return image_bytes


class Stage3VLMOrchestrator:
    """Main orchestrator for Stage 3: Set-of-Marks VLM Damage Inspection.

    Acts as an intelligent inspection orchestrator that:
    1. Evaluates vehicle orientation and component-wise damage consistency.
    2. Identifies and filters duplicate or repeating damage signatures.
    3. Detects unsegmented or missing damaged parts left out of upstream stages.
    4. Slices sub-crop image regions and sends them back to an identification model
       when orientation conflicts or component ambiguities arise.
    """

    def __init__(
        self,
        settings: Optional[Stage3Settings] = None,
        adapter: Optional[IVLMInspectionAdapter] = None,
        reidentification_service: Optional[Any] = None,
    ) -> None:
        self.settings = settings or stage3_settings
        self.adapter = adapter or get_vlm_adapter(self.settings)
        self.prompt_engine = VLMPromptEngine()
        self.forensic_engine = ForensicDecisionEngine()
        self.reidentification_service = reidentification_service

    async def _handle_reidentification(
        self,
        part: GroundedDamagedPart,
        raw_bytes: bytes,
        vlm_output: VLMInspectionOutput,
    ) -> None:
        """Send back image or cut ROI to identification model to resolve component identity."""
        if self.reidentification_service is None:
            return

        cut_bytes = _cut_roi_bytes(raw_bytes, vlm_output.reidentification_roi_bbox)
        try:
            reid_res: Any = None
            if hasattr(self.reidentification_service, "reidentify_component"):
                reid_res = await self.reidentification_service.reidentify_component(
                    crop_bytes=cut_bytes,
                    context_part=part.canonical_part_key,
                    roi_bbox=vlm_output.reidentification_roi_bbox,
                )
            elif hasattr(self.reidentification_service, "identify_crop"):
                reid_res = await self.reidentification_service.identify_crop(
                    image_bytes=cut_bytes,
                    crop_bbox=vlm_output.reidentification_roi_bbox,
                )
            elif callable(self.reidentification_service):
                reid_res = await self.reidentification_service(cut_bytes, vlm_output.reidentification_roi_bbox)

            if reid_res:
                corrected_key = (
                    reid_res
                    if isinstance(reid_res, str)
                    else getattr(reid_res, "canonical_part_key", str(reid_res))
                )
                logger.info(
                    "Re-identification model resolved %s -> %s",
                    part.canonical_part_key,
                    corrected_key,
                )
                part.canonical_part_key = corrected_key
                part.display_part_name = corrected_key.replace("_", " ").title()
        except Exception as reid_err:
            logger.warning(
                "Re-identification loop encountered error for %s: %s",
                part.canonical_part_key,
                reid_err,
            )

    async def inspect_claim(self, stage2_handoff: Stage3HandoffPayload) -> Stage4HandoffPayload:
        """Execute Stage 3 forensic damage inspection over candidate grounded parts from Stage 2.

        Lifecycle:
        1. Iterates through claimed grounded parts from Stage 2.
        2. Quarantines or skips unclaimed/pre-existing parts.
        3. Loads dual-crop image buffers (Image 1: cyan Set-of-Marks, Image 2: pristine raw).
        4. Contextualizes the inspection prompt via VLMPromptEngine.
        5. Calls the VLM inspection adapter with constrained structured output.
        6. Component-Wise & Orientation Verification:
           - Triggers sub-crop re-identification if orientation or component mismatch occurs.
        7. Deduplication Gate:
           - Quarantines candidate if it duplicates a previously verified part or damage signature.
        8. Missing Parts Aggregation:
           - Aggregates any omitted or unsegmented damage detected in surrounding context.
        9. Passes VLM output through ForensicDecisionEngine (evaluating rust fraud, safety,
           and false positive quarantine).
        10. Enforces the zero real damage gate (ESC-07) if no candidate damage is physically real.
        11. Packages verified and quarantined parts into the immutable Stage4HandoffPayload.
        """
        start_time = time.perf_counter()
        verified_parts: List[VerifiedDamagedPart] = []
        quarantined_parts: List[QuarantinedPartRecord] = []
        seen_verified_keys: set[str] = set()
        missing_parts_discovered: List[str] = []
        duplicates_quarantined_count = 0
        dynamic_recrops_count = 0

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

            # 2. Read visual evidence buffers (Image 1: SoM, Image 2: Pristine Raw, Image 3: Full Keyframe)
            som_bytes = _read_crop_bytes(part.som_annotated_crop_path)
            raw_bytes = _read_crop_bytes(part.som_raw_crop_path)
            full_frame_bytes = _read_crop_bytes(getattr(part, "som_full_annotated_path", None))

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
                som_full_annotated_path=getattr(part, "som_full_annotated_path", None),
            )

            # 4. Dispatch to VLM adapter with tri-stream visual evidence
            t0 = time.perf_counter()
            try:
                vlm_output: VLMInspectionOutput = await self.adapter.inspect_damage(
                    som_crop_bytes=som_bytes,
                    raw_crop_bytes=raw_bytes,
                    context=context,
                    full_frame_bytes=full_frame_bytes,
                )
            except TypeError as err:
                if "full_frame_bytes" in str(err):
                    vlm_output = await self.adapter.inspect_damage(
                        som_crop_bytes=som_bytes,
                        raw_crop_bytes=raw_bytes,
                        context=context,
                    )
                else:
                    raise
            part_latency_ms = (time.perf_counter() - t0) * 1000.0

            # 5. Dynamic Adaptive Recrop / Re-extraction Loop (Bounded depth = 1)
            if (
                vlm_output.harness_action == HarnessAction.REQUEST_DYNAMIC_RECROP
                and vlm_output.requested_crop_bbox
            ):
                logger.info(
                    "Harness requested dynamic recrop for %s: %s (bbox: %s)",
                    part.canonical_part_key,
                    vlm_output.reextraction_reason,
                    vlm_output.requested_crop_bbox,
                )
                adaptive_crop_bytes = _cut_roi_bytes(full_frame_bytes, vlm_output.requested_crop_bbox)
                dynamic_recrops_count += 1

                if vlm_output.needs_reidentification or not vlm_output.component_matches_target:
                    await self._handle_reidentification(part, adaptive_crop_bytes, vlm_output)

                recrop_t0 = time.perf_counter()
                recrop_context = InspectionContext(
                    canonical_part_key=part.canonical_part_key,
                    part_display_name=part.display_part_name,
                    primary_damage_class=part.primary_damage_class,
                    make=stage2_handoff.make,
                    model=stage2_handoff.model,
                    iop_ratio=iop_val,
                    is_claimed=getattr(part, "is_claimed", True),
                    claim_id=str(stage2_handoff.claim_id),
                    som_annotated_crop_path=part.som_annotated_crop_path,
                    som_raw_crop_path=part.som_raw_crop_path,
                    som_full_annotated_path=getattr(part, "som_full_annotated_path", None),
                )
                try:
                    re_vlm_output = await self.adapter.inspect_damage(
                        som_crop_bytes=adaptive_crop_bytes,
                        raw_crop_bytes=adaptive_crop_bytes,
                        context=recrop_context,
                        full_frame_bytes=full_frame_bytes,
                    )
                except TypeError as err:
                    if "full_frame_bytes" in str(err):
                        re_vlm_output = await self.adapter.inspect_damage(
                            som_crop_bytes=adaptive_crop_bytes,
                            raw_crop_bytes=adaptive_crop_bytes,
                            context=recrop_context,
                        )
                    else:
                        raise
                part_latency_ms += (time.perf_counter() - recrop_t0) * 1000.0
                if re_vlm_output.harness_action == HarnessAction.REQUEST_DYNAMIC_RECROP:
                    re_vlm_output.harness_action = HarnessAction.PASS
                vlm_output = re_vlm_output
            elif vlm_output.needs_reidentification or not vlm_output.component_matches_target:
                # Component-Wise Re-identification Loop
                await self._handle_reidentification(part, raw_bytes, vlm_output)

            # 6. Harness Quarantine Gate
            if vlm_output.harness_action == HarnessAction.QUARANTINE:
                reason = (
                    vlm_output.false_positive_reason
                    if not vlm_output.is_real_physical_damage
                    else FalsePositiveReason.OTHER_NON_DAMAGE
                )
                quarantined_parts.append(
                    QuarantinedPartRecord(
                        canonical_part_key=part.canonical_part_key,
                        primary_damage_class=part.primary_damage_class,
                        false_positive_reason=reason,
                        visual_reasoning_short=vlm_output.visual_reasoning_short,
                        vlm_confidence=vlm_output.confidence,
                        som_crop_path=part.som_annotated_crop_path,
                        latency_ms=part_latency_ms,
                        vehicle_orientation=vlm_output.vehicle_orientation,
                        harness_action=HarnessAction.QUARANTINE,
                        reextraction_reason=vlm_output.reextraction_reason,
                    )
                )
                continue

            # 7. Deduplication Check
            is_duplicate = (
                vlm_output.possible_duplicate
                or part.canonical_part_key in seen_verified_keys
                or (
                    vlm_output.duplicate_of_part_key
                    and vlm_output.duplicate_of_part_key in seen_verified_keys
                )
            )

            if is_duplicate:
                dup_target = vlm_output.duplicate_of_part_key or part.canonical_part_key
                logger.info(
                    "Candidate part %s identified as duplicate of %s; quarantining from repair schedule.",
                    part.canonical_part_key,
                    dup_target,
                )
                quarantined_parts.append(
                    QuarantinedPartRecord(
                        canonical_part_key=part.canonical_part_key,
                        primary_damage_class=part.primary_damage_class,
                        false_positive_reason=FalsePositiveReason.DUPLICATE_DAMAGE,
                        visual_reasoning_short=f"Duplicate damage signature repeating {dup_target}.",
                        vlm_confidence=vlm_output.confidence,
                        som_crop_path=part.som_annotated_crop_path,
                        latency_ms=part_latency_ms,
                        vehicle_orientation=vlm_output.vehicle_orientation,
                        is_duplicate=True,
                        duplicate_of_part=dup_target,
                        harness_action=HarnessAction.QUARANTINE,
                        reextraction_reason="Duplicate damage signature.",
                    )
                )
                duplicates_quarantined_count += 1
                continue

            # 8. Missing Parts Aggregation
            if vlm_output.missing_parts_detected:
                for mp in vlm_output.missing_parts_detected:
                    if mp and mp not in missing_parts_discovered:
                        missing_parts_discovered.append(mp)

            # 9. Evaluate result with ForensicDecisionEngine (may raise ESC-04 or ESC-06)
            decision = self.forensic_engine.validate_inspection_result(
                part=part,
                vlm_output=vlm_output,
                latency_ms=part_latency_ms,
                claim_id=str(stage2_handoff.claim_id),
            )

            # 10. Accumulate into verified or quarantined partition
            if isinstance(decision, VerifiedDamagedPart):
                verified_parts.append(decision)
                seen_verified_keys.add(decision.canonical_part_key)
            elif isinstance(decision, QuarantinedPartRecord):
                quarantined_parts.append(decision)

        # 10. Zero Real Damage Gate (ESC-07)
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

        # 11. Assemble Stage 3 Telemetry
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
            "duplicates_quarantined_count": duplicates_quarantined_count,
            "dynamic_recrops_count": dynamic_recrops_count,
            "missing_parts_detected": missing_parts_discovered,
            "status": "S3_PASSED",
        }

        # Merge with upstream telemetry from Stage 2
        combined_telemetry = dict(getattr(stage2_handoff, "telemetry", {}))
        combined_telemetry["stage3_telemetry"] = stage3_telemetry

        logger.info(
            "Stage 3 completed for claim %s in %.2fms (%d verified, %d quarantined, %d duplicates, %d missing parts)",
            stage2_handoff.claim_id,
            total_latency_ms,
            len(verified_parts),
            len(quarantined_parts),
            duplicates_quarantined_count,
            len(missing_parts_discovered),
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
