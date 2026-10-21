"""Forensic decision and reality validation engine for Stage 3 VLM Damage Inspection."""

from __future__ import annotations

import logging
from typing import Optional, Union

from app.domain.dual_mask_segmentation.schemas import GroundedDamagedPart
from app.domain.vlm_damage_inspection.exceptions import (
    Stage3MalformedOutputError,
    Stage3RustOrOxidationError,
    Stage3StructuralMisalignmentError,
)
from app.domain.vlm_damage_inspection.schemas import (
    DepthGrade,
    FalsePositiveReason,
    QuarantinedPartRecord,
    VerifiedDamagedPart,
    VLMInspectionOutput,
)

logger = logging.getLogger(__name__)


class ForensicDecisionEngine:
    """Forensic evaluation engine evaluating VLM visual inspections against physical fraud/safety gates."""

    def __init__(self) -> None:
        self._valid_depth_grades = set(DepthGrade)

    def validate_inspection_result(
        self,
        part: GroundedDamagedPart,
        vlm_output: VLMInspectionOutput,
        latency_ms: float = 0.0,
        claim_id: Optional[str] = None,
    ) -> Union[VerifiedDamagedPart, QuarantinedPartRecord]:
        """Evaluate VLMInspectionOutput against forensic fraud, safety, and physical reality gates.

        1. Real Damage Check:
           If `not vlm_output.is_real_physical_damage`:
           Records a `QuarantinedPartRecord` (false positive reason, visual reasoning) and marks part
           as excluded from billable repair schedule. Telemetry status: `S3_FALSE_POSITIVE_FILTERED`.

        2. Rust / Oxidation Gate (`ESC-04`):
           If `vlm_output.has_rust_or_oxidation`:
           Raises `Stage3RustOrOxidationError` with failure code `ESC_04_PREEXISTING_CORROSION`.

        3. Structural Misalignment Gate (`ESC-06`):
           If `vlm_output.has_panel_gap_misalignment`:
           Raises `Stage3StructuralMisalignmentError` with failure code `ESC_06_STRUCTURAL_HAZARD`.

        4. Depth Grade Validation:
           Confirms `depth_grade` is valid enum value (L1 ... L5).

        5. Returns `VerifiedDamagedPart` containing all original `GroundedDamagedPart` data plus
           `depth_grade`, `vlm_confidence`, `visual_reasoning_short`, and `raw_vlm_output`.
        """
        # --- Gate 1: Pre-Existing Rust / Oxidation Gate (ESC-04) ---
        if vlm_output.has_rust_or_oxidation:
            details = vlm_output.rust_details or vlm_output.visual_reasoning_short or "Active corrosion detected."
            msg = f"Pre-existing rust/oxidation detected on {part.canonical_part_key}: {details}"
            logger.warning("[ESC-04] Fraud gate triggered for part %s: %s", part.canonical_part_key, msg)
            raise Stage3RustOrOxidationError(
                message=msg,
                part_key=part.canonical_part_key,
                claim_id=claim_id,
                evidence_path=part.som_annotated_crop_path,
            )

        # --- Gate 2: Structural Alignment & Chassis Distortion Gate (ESC-06) ---
        if vlm_output.has_panel_gap_misalignment:
            details = (
                vlm_output.misalignment_details
                or vlm_output.visual_reasoning_short
                or "Panel gap / frame misalignment detected."
            )
            msg = f"Panel gap misalignment detected on {part.canonical_part_key}: {details}"
            logger.warning("[ESC-06] Safety gate triggered for part %s: %s", part.canonical_part_key, msg)
            raise Stage3StructuralMisalignmentError(
                message=msg,
                part_key=part.canonical_part_key,
                claim_id=claim_id,
                evidence_path=part.som_annotated_crop_path,
            )

        # --- Gate 3: Physical Reality Check (False Positive Filtering) ---
        if not vlm_output.is_real_physical_damage:
            fp_reason = vlm_output.false_positive_reason
            if fp_reason == FalsePositiveReason.NONE:
                fp_reason = FalsePositiveReason.OTHER_NON_DAMAGE

            logger.info(
                "[S3_FALSE_POSITIVE_FILTERED] Candidate part %s quarantined: reason=%s, reasoning=%s",
                part.canonical_part_key,
                fp_reason.value,
                vlm_output.visual_reasoning_short,
            )
            return QuarantinedPartRecord(
                canonical_part_key=part.canonical_part_key,
                primary_damage_class=part.primary_damage_class,
                false_positive_reason=fp_reason,
                visual_reasoning_short=vlm_output.visual_reasoning_short,
                vlm_confidence=vlm_output.confidence,
                som_crop_path=part.som_annotated_crop_path,
                latency_ms=latency_ms,
            )

        # --- Gate 4: Depth Grade Validation (L1 .. L5) ---
        depth_grade = vlm_output.depth_grade
        if isinstance(depth_grade, str):
            try:
                depth_grade = DepthGrade(depth_grade)
            except ValueError as err:
                raise Stage3MalformedOutputError(
                    f"Invalid depth grade '{depth_grade}' returned by VLM for {part.canonical_part_key}."
                ) from err

        if depth_grade not in self._valid_depth_grades:
            raise Stage3MalformedOutputError(
                f"Unknown depth grade value '{depth_grade}' for {part.canonical_part_key}."
            )

        # --- Gate 5: Construct and Return VerifiedDamagedPart ---
        verified_part = VerifiedDamagedPart.from_grounded_part(
            grounded_part=part,
            vlm_output=vlm_output,
            latency_ms=latency_ms,
        )
        # Ensure depth grade matches validated enum instance
        verified_part.depth_grade = depth_grade

        logger.info(
            "Part %s verified with forensic depth grade %s (confidence=%.2f)",
            part.canonical_part_key,
            depth_grade.value,
            vlm_output.confidence,
        )
        return verified_part
