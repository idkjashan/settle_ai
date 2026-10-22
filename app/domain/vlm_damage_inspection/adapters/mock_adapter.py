"""Zero-network deterministic mock adapter for headless testing and CI/CD validation."""

from __future__ import annotations

from app.domain.vlm_damage_inspection.adapters.interfaces import IVLMInspectionAdapter
from app.domain.vlm_damage_inspection.schemas import (
    DepthGrade,
    FalsePositiveReason,
    InspectionContext,
    VehicleOrientation,
    VLMInspectionOutput,
)


class DeterministicMockVLMAdapter(IVLMInspectionAdapter):
    """Zero-network deterministic adapter executing in < 5ms without external dependencies."""

    async def inspect_damage(
        self,
        som_crop_bytes: bytes,
        raw_crop_bytes: bytes,
        context: InspectionContext,
    ) -> VLMInspectionOutput:
        # Build search text across paths and context identifiers
        text_corpus = " ".join([
            str(context.som_annotated_crop_path or ""),
            str(context.som_raw_crop_path or ""),
            context.canonical_part_key,
            context.primary_damage_class,
            context.part_display_name,
        ]).lower()

        # Orientation inference heuristic for test fixtures
        orientation = VehicleOrientation.FRONT
        if any(w in text_corpus for w in ("rear", "back", "boot", "trunk", "tailgate")):
            orientation = VehicleOrientation.REAR
        elif "left" in text_corpus:
            orientation = VehicleOrientation.LEFT_SIDE
        elif "right" in text_corpus:
            orientation = VehicleOrientation.RIGHT_SIDE
        elif "roof" in text_corpus:
            orientation = VehicleOrientation.OVERHEAD_ROOF

        is_duplicate = "duplicate" in text_corpus
        duplicate_of = context.canonical_part_key.replace("_duplicate", "") if is_duplicate else None
        missing_parts = ["fog_lamp_bezel_left", "tow_eye_cap"] if "missing" in text_corpus else []
        needs_reid = "reidentify" in text_corpus or "mismatch" in text_corpus
        comp_matches = not ("mismatch" in text_corpus)

        # 1. Check for simulated pre-existing rust / oxidation fixture (ESC-04)
        if "rust" in text_corpus or "oxidation" in text_corpus or "corrosion" in text_corpus:
            return VLMInspectionOutput(
                is_real_physical_damage=True,
                false_positive_reason=FalsePositiveReason.NONE,
                depth_grade=DepthGrade.L2_BASECOAT_SCRATCH,
                has_rust_or_oxidation=True,
                rust_details="Reddish-brown iron oxide (Fe2O3) flaking detected along gouge edge.",
                has_panel_gap_misalignment=False,
                misalignment_details=None,
                confidence=0.98,
                visual_reasoning_short="Pre-existing corrosion detected inside damage boundary.",
            )

        # 2. Check for simulated structural frame misalignment fixture (ESC-06)
        if any(w in text_corpus for w in ("misalign", "frame", "gap", "wedged", "chassis")):
            return VLMInspectionOutput(
                is_real_physical_damage=True,
                false_positive_reason=FalsePositiveReason.NONE,
                depth_grade=DepthGrade.L4_CREASED_DENT,
                has_rust_or_oxidation=False,
                rust_details=None,
                has_panel_gap_misalignment=True,
                misalignment_details="Door margin wedged: 9mm at upper edge tapering to 0mm at lower latch.",
                confidence=0.96,
                visual_reasoning_short="Structural pillar displacement causing uneven door seam.",
            )

        # 3. Check for simulated false positive surface contaminants / glare
        if any(w in text_corpus for w in ("dirt", "mud", "glare", "bird", "droppings", "reflection", "chalk", "sticker", "decal", "water")):
            reason = FalsePositiveReason.MUD_OR_DIRT
            if "bird" in text_corpus or "droppings" in text_corpus:
                reason = FalsePositiveReason.BIRD_DROPPINGS
            elif "glare" in text_corpus:
                reason = FalsePositiveReason.SPECULAR_GLARE
            elif "chalk" in text_corpus or "marker" in text_corpus:
                reason = FalsePositiveReason.CHALK_OR_MARKER
            elif "sticker" in text_corpus or "decal" in text_corpus:
                reason = FalsePositiveReason.DECAL_OR_STICKER
            elif "water" in text_corpus or "droplet" in text_corpus:
                reason = FalsePositiveReason.WATER_DROPLET
            elif "reflection" in text_corpus or "asphalt" in text_corpus:
                reason = FalsePositiveReason.ASPHALT_REFLECTION

            return VLMInspectionOutput(
                is_real_physical_damage=False,
                false_positive_reason=reason,
                depth_grade=DepthGrade.L1_SURFACE_SCUFF,
                has_rust_or_oxidation=False,
                rust_details=None,
                has_panel_gap_misalignment=False,
                misalignment_details=None,
                confidence=0.95,
                visual_reasoning_short=f"Non-physical surface contaminant identified: {reason.value}.",
            )

        # 4. Deterministic physical damage depth mapping based on damage class & IoP
        dmg = context.primary_damage_class.lower()
        iop = getattr(context, "final_iop_ratio", context.iop_ratio)

        if dmg in ("crack", "puncture", "glass_shatter", "lamp_broken", "tear"):
            grade = DepthGrade.L5_STRUCTURAL_TEAR
        elif dmg == "dent":
            grade = DepthGrade.L3_SHALLOW_DENT_PDR if iop <= 0.10 else DepthGrade.L4_CREASED_DENT
        elif dmg == "scratch":
            grade = DepthGrade.L2_BASECOAT_SCRATCH
        else:
            grade = DepthGrade.L1_SURFACE_SCUFF

        return VLMInspectionOutput(
            is_real_physical_damage=True,
            false_positive_reason=FalsePositiveReason.NONE,
            depth_grade=grade,
            has_rust_or_oxidation=False,
            rust_details=None,
            has_panel_gap_misalignment=False,
            misalignment_details=None,
            confidence=0.92,
            visual_reasoning_short=f"Verified real {dmg} damage requiring {grade.value} repair intervention.",
        )

    async def health_check(self) -> bool:
        """Deterministic mock adapter is always healthy."""
        return True
