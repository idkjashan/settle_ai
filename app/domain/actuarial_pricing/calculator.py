"""
app/domain/actuarial_pricing/calculator.py
Pure functional Actuarial Calculator engine. Zero LLM math, 100% Python Decimal.
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.domain.actuarial_pricing.enums import (
    MaterialType,
    PaintType,
    RepairAction,
)
from app.domain.actuarial_pricing.exceptions import (
    Stage4CataloguePartNotFoundError,
    Stage4FinancialCeilingExceededError,
)
from app.domain.actuarial_pricing.rules import (
    AUTONOMOUS_CEILING_INR,
    calculate_denting_labor_multiplier,
    determine_repair_action,
    get_paint_type_multiplier,
    get_part_depreciation_rate,
    get_salvage_deduction_rate,
    quantize_inr,
    resolve_paint_overlap_factors,
)
from app.domain.actuarial_pricing.schemas import (
    ActuarialLineItemDTO,
    ActuarialSummaryDTO,
    CashSettlementBandDTO,
    PolicyPricingContextDTO,
)
from app.domain.vlm_damage_inspection.schemas import VerifiedDamagedPart
from app.infrastructure.db.models import OemPart


def _get_val(obj: Any, key: str, default: Any = None) -> Any:
    """Safely extract attribute or dict value from heterogeneous objects."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class ActuarialCalculator:
    """
    Pure deterministic pricing calculator for automobile own-damage claims.
    Enforces the Indian Motor Tariff (IMT) and IRDAI statutory calculation rules.
    Operates strictly with Python Decimal ROUND_HALF_UP to two decimal places (0.01).
    """

    GST_RATE = Decimal("0.18")
    INITIAL_OFFER_RATIO = Decimal("0.75")
    TARGET_OFFER_RATIO = Decimal("0.85")
    MAX_CAP_RATIO = Decimal("0.95")

    def calculate(
        self,
        policy_context: PolicyPricingContextDTO,
        verified_parts: List[VerifiedDamagedPart],
        oem_catalog: Dict[str, OemPart],
        current_year: int = 2026,
    ) -> Tuple[List[ActuarialLineItemDTO], ActuarialSummaryDTO, CashSettlementBandDTO]:
        """
        Compute auditable line items, summary, and settlement band for a claim.

        Args:
            policy_context: Ingested policy and vehicle terms.
            verified_parts: Verified forensic damaged parts from Stage 3.
            oem_catalog: Map of canonical_part_key -> OemPart record.
            current_year: Reference calendar year for age computation.

        Returns:
            Tuple of (line_items, summary, settlement_band).

        Raises:
            Stage4CataloguePartNotFoundError: If a damaged part key is missing from catalogue.
            Stage4FinancialCeilingExceededError: If gross garage repair > ₹25,000.00 (ESC-08).
        """
        mfg_year = int(_get_val(policy_context, "manufacturing_year", current_year))
        vehicle_age = max(0.0, float(current_year - mfg_year))

        # Resolve paint type and multiplier
        raw_paint_type = _get_val(policy_context, "paint_type", PaintType.METALLIC)
        if isinstance(raw_paint_type, str):
            try:
                paint_type = PaintType(raw_paint_type.lower())
            except ValueError:
                paint_type = PaintType.METALLIC
        else:
            paint_type = raw_paint_type

        paint_multiplier = get_paint_type_multiplier(paint_type)
        is_zero_dep = bool(_get_val(policy_context, "zero_dep_addon", True))

        # 1. First Pass: Identify panels requiring painting for overlap discount calculation
        paintable_panels: List[Tuple[str, Decimal]] = []
        for part in verified_parts:
            part_key = str(_get_val(part, "canonical_part_key"))
            if part_key not in oem_catalog:
                make = str(_get_val(policy_context, "make", "UNKNOWN"))
                model = str(_get_val(policy_context, "model", "UNKNOWN"))
                raise Stage4CataloguePartNotFoundError(
                    make=make,
                    model=model,
                    canonical_part_key=part_key,
                )

            oem = oem_catalog[part_key]
            material_val = _get_val(oem, "part_material", "metal")
            if isinstance(material_val, MaterialType):
                material = material_val
            else:
                try:
                    material = MaterialType(str(material_val).lower())
                except ValueError:
                    material = MaterialType.METAL

            is_repairable = bool(_get_val(oem, "is_repairable", True)) and bool(
                _get_val(part, "is_repairable", True)
            )
            depth_grade_raw = _get_val(part, "depth_grade", "L1_SURFACE_SCUFF")
            depth_grade_str = (
                depth_grade_raw.value
                if hasattr(depth_grade_raw, "value")
                else str(depth_grade_raw)
            )
            iop_ratio = float(
                _get_val(part, "final_iop_ratio", _get_val(part, "iop_ratio", 0.0))
            )

            action = determine_repair_action(
                is_repairable=is_repairable,
                depth_grade=depth_grade_str,
                iop_ratio=iop_ratio,
            )

            full_panel_paint = Decimal(str(_get_val(oem, "full_panel_paint_inr", "0.00")))
            needs_paint = False
            if material != MaterialType.GLASS and full_panel_paint > Decimal("0.00"):
                if action == RepairAction.REPLACE:
                    needs_paint = True
                elif action == RepairAction.REPAIR and depth_grade_str in (
                    "L2_BASECOAT_SCRATCH",
                    "L4_CREASED_DENT",
                ):
                    needs_paint = True

            if needs_paint:
                paintable_panels.append((part_key, full_panel_paint))

        # Multi-panel adjacent paint overlap discount: 1st panel 100%, 2nd+ panels 80% (20% discount)
        overlap_map: Dict[str, Decimal] = dict(resolve_paint_overlap_factors(paintable_panels))

        # 2. Second Pass: Itemized Line-Item Financial Computation
        line_items: List[ActuarialLineItemDTO] = []
        for part in verified_parts:
            part_key = str(_get_val(part, "canonical_part_key"))
            oem = oem_catalog[part_key]

            material_val = _get_val(oem, "part_material", "metal")
            if isinstance(material_val, MaterialType):
                material = material_val
            else:
                try:
                    material = MaterialType(str(material_val).lower())
                except ValueError:
                    material = MaterialType.METAL

            is_repairable = bool(_get_val(oem, "is_repairable", True)) and bool(
                _get_val(part, "is_repairable", True)
            )
            depth_grade_raw = _get_val(part, "depth_grade", "L1_SURFACE_SCUFF")
            depth_grade_str = (
                depth_grade_raw.value
                if hasattr(depth_grade_raw, "value")
                else str(depth_grade_raw)
            )
            iop_ratio = float(
                _get_val(part, "final_iop_ratio", _get_val(part, "iop_ratio", 0.0))
            )

            action = determine_repair_action(
                is_repairable=is_repairable,
                depth_grade=depth_grade_str,
                iop_ratio=iop_ratio,
            )

            display_name = str(_get_val(oem, "display_part_name", part_key))
            part_number = str(_get_val(oem, "oem_part_number", "OEM-GENERIC"))

            # A. Parts Pricing, Depreciation & Salvage
            if action == RepairAction.REPLACE:
                base_part_cost = quantize_inr(
                    Decimal(str(_get_val(oem, "oem_part_cost_inr", "0.00")))
                )
                dep_rate = get_part_depreciation_rate(
                    material=material,
                    vehicle_age_years=vehicle_age,
                    is_zero_dep=is_zero_dep,
                )
                dep_amount = quantize_inr(base_part_cost * dep_rate)
                net_part_cost = quantize_inr(base_part_cost - dep_amount)
                salvage_rate = get_salvage_deduction_rate(material, action)
                salvage_deduction = quantize_inr(net_part_cost * salvage_rate)
                rr_labour = quantize_inr(
                    Decimal(str(_get_val(oem, "rr_labour_inr", "0.00")))
                )
                denting_labour = Decimal("0.00")
                pdr_flat = Decimal("0.00")
            else:  # REPAIR
                base_part_cost = Decimal("0.00")
                dep_rate = Decimal("0.00")
                dep_amount = Decimal("0.00")
                net_part_cost = Decimal("0.00")
                salvage_deduction = Decimal("0.00")
                rr_labour = Decimal("0.00")

                if depth_grade_str in ("L1_SURFACE_SCUFF", "L3_SHALLOW_DENT_PDR"):
                    pdr_flat = quantize_inr(
                        Decimal(str(_get_val(oem, "pdr_or_polish_flat_inr", "0.00")))
                    )
                    denting_labour = Decimal("0.00")
                elif depth_grade_str == "L4_CREASED_DENT":
                    pdr_flat = Decimal("0.00")
                    gamma_iop = calculate_denting_labor_multiplier(iop_ratio)
                    base_denting = Decimal(
                        str(_get_val(oem, "denting_base_labour_inr", "0.00"))
                    )
                    denting_labour = quantize_inr(base_denting * gamma_iop)
                else:  # L2_BASECOAT_SCRATCH or other superficial repair
                    pdr_flat = Decimal("0.00")
                    denting_labour = Decimal("0.00")

            # B. Paint Pricing & Overlap Schedule
            overlap_factor = overlap_map.get(part_key, Decimal("0.00"))
            if overlap_factor > Decimal("0.00"):
                base_paint = quantize_inr(
                    Decimal(str(_get_val(oem, "full_panel_paint_inr", "0.00")))
                )
                final_paint = quantize_inr(base_paint * paint_multiplier * overlap_factor)
                paint_overlap_discount = quantize_inr(
                    (Decimal("1.00") - overlap_factor) * Decimal("100.0")
                )
            else:
                base_paint = Decimal("0.00")
                final_paint = Decimal("0.00")
                paint_overlap_discount = Decimal("0.00")

            # C. Pre-Tax Totals and Statutory 18% GST
            pre_tax_total = quantize_inr(
                net_part_cost + rr_labour + denting_labour + pdr_flat + final_paint
            )
            gst_amount = quantize_inr(pre_tax_total * self.GST_RATE)
            gross_line_item = quantize_inr(pre_tax_total + gst_amount)

            line_items.append(
                ActuarialLineItemDTO(
                    canonical_part_key=part_key,
                    display_part_name=display_name,
                    oem_part_number=part_number,
                    material=material,
                    action=action,
                    depth_grade=depth_grade_str,
                    iop_ratio=iop_ratio,
                    base_part_cost_inr=base_part_cost,
                    depreciation_rate_pct=quantize_inr(dep_rate * Decimal("100.0")),
                    depreciation_amount_inr=dep_amount,
                    net_part_cost_inr=net_part_cost,
                    salvage_deduction_inr=salvage_deduction,
                    rr_labour_inr=rr_labour,
                    denting_labour_inr=denting_labour,
                    pdr_polish_flat_inr=pdr_flat,
                    base_paint_inr=base_paint,
                    paint_multiplier=paint_multiplier,
                    paint_overlap_discount=paint_overlap_discount,
                    final_paint_inr=final_paint,
                    pre_tax_total_inr=pre_tax_total,
                    gst_amount_inr=gst_amount,
                    gross_line_item_total_inr=gross_line_item,
                )
            )

        # 3. Aggregations & Summary
        tot_gross_parts = sum(
            (item.base_part_cost_inr for item in line_items), Decimal("0.00")
        )
        tot_dep = sum(
            (item.depreciation_amount_inr for item in line_items), Decimal("0.00")
        )
        tot_net_parts = sum(
            (item.net_part_cost_inr for item in line_items), Decimal("0.00")
        )
        tot_labour = sum(
            (
                item.rr_labour_inr + item.denting_labour_inr + item.pdr_polish_flat_inr
                for item in line_items
            ),
            Decimal("0.00"),
        )
        tot_paint = sum((item.final_paint_inr for item in line_items), Decimal("0.00"))
        pre_tax_subtotal = quantize_inr(tot_net_parts + tot_labour + tot_paint)
        tot_gst = quantize_inr(pre_tax_subtotal * self.GST_RATE)
        gross_garage_repair = quantize_inr(pre_tax_subtotal + tot_gst)
        tot_salvage = sum(
            (item.salvage_deduction_inr for item in line_items), Decimal("0.00")
        )

        # Statutory & Voluntary Deductibles
        compulsory_deductible = Decimal(
            str(_get_val(policy_context, "compulsory_deductible_inr", "1000.00"))
        )
        engine_cc = _get_val(policy_context, "engine_cc", None)
        if engine_cc is not None and int(engine_cc) > 1500 and compulsory_deductible == Decimal("1000.00"):
            compulsory_deductible = Decimal("2000.00")

        compulsory_deductible = quantize_inr(compulsory_deductible)
        voluntary_deductible = quantize_inr(
            Decimal(str(_get_val(policy_context, "voluntary_deductible_inr", "0.00")))
        )
        tot_deductibles = quantize_inr(compulsory_deductible + voluntary_deductible)

        # Net Claim Liability: C_net = max(0.00, GrossGarage - Salvage - TotalDeductibles)
        payable_before_deductibles = quantize_inr(gross_garage_repair - tot_salvage)
        net_claim_liability = quantize_inr(
            max(Decimal("0.00"), payable_before_deductibles - tot_deductibles)
        )

        summary = ActuarialSummaryDTO(
            total_gross_parts_inr=tot_gross_parts,
            total_depreciation_inr=tot_dep,
            total_net_parts_inr=tot_net_parts,
            total_labour_inr=tot_labour,
            total_paint_inr=tot_paint,
            pre_tax_subtotal_inr=pre_tax_subtotal,
            total_gst_inr=tot_gst,
            gross_garage_repair_inr=gross_garage_repair,
            total_salvage_deduction_inr=tot_salvage,
            compulsory_deductible_inr=compulsory_deductible,
            voluntary_deductible_inr=voluntary_deductible,
            total_deductible_inr=tot_deductibles,
            net_claim_liability_inr=net_claim_liability,
        )

        # 4. Guardrail: Autonomous Financial Ceiling (ESC-08)
        if gross_garage_repair > AUTONOMOUS_CEILING_INR:
            raise Stage4FinancialCeilingExceededError(
                gross_amount_inr=str(gross_garage_repair),
                ceiling_inr=str(AUTONOMOUS_CEILING_INR),
            )

        # 5. Cash-in-Lieu Settlement Band: O_0 = 75%, O_target = 85%, O_max = min(₹25,000, 95%)
        initial_offer = quantize_inr(net_claim_liability * self.INITIAL_OFFER_RATIO)
        target_settlement = quantize_inr(net_claim_liability * self.TARGET_OFFER_RATIO)
        walkaway_cap = quantize_inr(
            min(AUTONOMOUS_CEILING_INR, net_claim_liability * self.MAX_CAP_RATIO)
        )

        band = CashSettlementBandDTO(
            initial_offer_inr=initial_offer,
            target_settlement_inr=target_settlement,
            walkaway_cap_inr=walkaway_cap,
            financial_ceiling_inr=AUTONOMOUS_CEILING_INR,
        )

        return line_items, summary, band
