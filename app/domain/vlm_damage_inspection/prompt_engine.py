"""Forensic prompt engine for Stage 3 Set-of-Marks VLM Damage Inspection."""

from __future__ import annotations

from typing import Optional

from app.domain.vlm_damage_inspection.prompts import SYSTEM_PROMPT as BASE_SYSTEM_PROMPT
from app.domain.vlm_damage_inspection.schemas import InspectionContext


class VLMPromptEngine:
    """Forensic prompt builder assembling physical reality instructions and dual-crop context."""

    SYSTEM_PROMPT: str = BASE_SYSTEM_PROMPT

    def __init__(self, custom_system_prompt: Optional[str] = None) -> None:
        self._system_prompt = custom_system_prompt or self.SYSTEM_PROMPT

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @classmethod
    def build_inspection_prompt(cls, context: InspectionContext) -> str:
        """Build the contextualized inspection prompt for a candidate vehicle part.

        Includes:
        - Vehicle make and model
        - Target component (part_display_name and canonical_part_key)
        - Stage 2 detected primary damage class
        - Intersection over Part (IoP) ratio and percentage
        - Explicit instructions on contrasting Image 1 (dilated cyan Set-of-Marks outline)
          against Image 2 (unmarked pristine raw crop)
        - Vehicle orientation, component-wise verification, duplicate damage detection,
          missing parts detection, and re-identification routing
        - Mandatory JSON schema field population instructions for VLMInspectionOutput
        """
        iop_val = getattr(context, "final_iop_ratio", getattr(context, "iop_ratio", 0.0))
        iop_pct = iop_val * 100.0 if iop_val <= 1.0 else iop_val
        part_display = context.part_display_name or context.canonical_part_key

        return f"""INSPECTION CONTEXT:
- Vehicle: {context.make} {context.model}
- Target Component: {part_display} (canonical_key: {context.canonical_part_key})
- Stage 2 Detected Damage Class: {context.primary_damage_class}
- Intersection over Part (IoP): {iop_pct:.1f}% ({iop_val:.3f} ratio)

INSPECTION INSTRUCTIONS & DUAL-CROP CONTRAST:
1. SPATIAL ANCHOR - Image 1 (Set-of-Marks):
   - Locate the candidate damage zone demarcated by the exterior cyan contour overlay in Image 1.
   - Use Image 1 STRICTLY as a spatial locator to identify the target zone.

2. TACTILE REALITY & SURFACE EXAMINATION - Image 2 (Raw Crop):
   - Cross-examine the exact same pixel coordinates in Image 2 (the pristine, unannotated raw crop).
   - Evaluate true surface texture, reflection continuity, clearcoat depth, bare primer, and metal substrate without annotation interference.

3. PHYSICAL REALITY GROUNDING (False Positive Filtering):
   - Determine if the candidate feature is real physical structural or paint damage (scuff, scratch, dent, tear, hole).
   - If it is a superficial surface contaminant (mud/dirt clumps, bird droppings, chalk/wax grease pencil, vinyl decal/sticker, rain droplet, specular glare flare, or asphalt reflection), set is_real_physical_damage = false and identify the false_positive_reason.

4. 5-GRADE DEPTH SEVERITY CLASSIFICATION:
   - If real physical damage, classify depth severity:
     * L1_SURFACE_SCUFF: Top clearcoat abrasion or paint transfer. Buffable. Zero metal deformation.
     * L2_BASECOAT_SCRATCH: Gouge through clearcoat into colored basecoat or grey e-coat primer. Substrate flat.
     * L3_SHALLOW_DENT_PDR: Smooth concave sheet metal bowl. Paint 100% intact. No sharp crease line.
     * L4_CREASED_DENT: Deep fold or sharp character line kink. Paint micro-fractured or peeled along ridge.
     * L5_STRUCTURAL_TEAR: Cracked plastic fascia, torn sheet metal, broken lamp lens, severed mounting tabs.

5. FRAUD GATE (ESC-04: Pre-Existing Rust / Oxidation):
   - Accidental loss covers fresh damage. Fresh collision reveals bright silver bare metal or grey e-coat.
   - If exposed metal shows reddish-brown iron rust (Fe2O3), powdery oxidation bloom, settled road grime in dent cavities, or weathered paint peeling, you MUST flag has_rust_or_oxidation = true and detail findings in rust_details.

6. SAFETY GATE (ESC-06: Structural Frame Misalignment):
   - Inspect adjacent body panel margins and seams.
   - If seams are pinched, overlapping, or wedged (e.g., tapering unevenly from top to bottom) indicating unibody chassis twist or pillar displacement, you MUST flag has_panel_gap_misalignment = true and detail findings in misalignment_details.

7. VEHICLE ORIENTATION & PERSPECTIVE GROUNDING:
   - Determine the visual orientation of the vehicle (FRONT, REAR, LEFT_SIDE, RIGHT_SIDE, FRONT_LEFT_3_QUARTER, FRONT_RIGHT_3_QUARTER, REAR_LEFT_3_QUARTER, REAR_RIGHT_3_QUARTER, OVERHEAD_ROOF, UNKNOWN) in vehicle_orientation.
   - Verify if this viewpoint geometrically matches the candidate component.

8. COMPONENT-WISE VERIFICATION:
   - Verify whether the damage is actually on the designated component ({context.canonical_part_key}).
   - Populate detected_component with the physical part name observed, and set component_matches_target to true or false.

9. DUPLICATE DAMAGE DETECTION:
   - Verify if this damage is a repeated or duplicate observation of damage from an overlapping view/keyframe.
   - Set possible_duplicate to true and specify duplicate_of_part_key if repeating.

10. MISSING / UNSEGMENTED PART DISCOVERY:
   - Check the surrounding panel area in Image 2 for adjacent missing, detached, or damaged parts that were left out.
   - List any omitted damaged parts in missing_parts_detected.

11. RE-IDENTIFICATION ORCHESTRATION:
   - If component identity is ambiguous or needs sub-crop re-verification, set needs_reidentification to true and supply reidentification_roi_bbox.

12. STRUCTURED JSON OUTPUT:
   - Output STRICTLY valid JSON matching the VLMInspectionOutput schema:
     {{"is_real_physical_damage": bool, "false_positive_reason": str, "depth_grade": str, "has_rust_or_oxidation": bool, "rust_details": str | null, "has_panel_gap_misalignment": bool, "misalignment_details": str | null, "confidence": float, "visual_reasoning_short": str, "vehicle_orientation": str, "detected_component": str | null, "component_matches_target": bool, "possible_duplicate": bool, "duplicate_of_part_key": str | null, "missing_parts_detected": list[str], "needs_reidentification": bool, "reidentification_roi_bbox": list[float] | null}}"""
