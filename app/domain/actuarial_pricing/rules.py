"""
app/domain/actuarial_pricing/rules.py
Statutory rules under the Indian Motor Tariff (IMT) and IRDAI guidelines.
100% deterministic pure functions using Python Decimal and ROUND_HALF_UP.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, List, Optional, Tuple
from app.domain.actuarial_pricing.enums import (
    MaterialType,
    PaintType,
    RepairAction,
)

TWOPLACES = Decimal("0.01")
AUTONOMOUS_CEILING_INR = Decimal("75000.00")  # ponytail: raised for hackathon demo; upgrade path → per-policy ceiling from InsuredPolicy.sum_insured
OVERLAP_DISCOUNT_FACTOR = Decimal("0.80")
STANDARD_GST_RATE = Decimal("0.18")


def quantize_paisa(value: Decimal | float | int | str) -> Decimal:
    """Quantize a monetary value strictly to 2 decimal places (paisa) using ROUND_HALF_UP."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


# Alias per LLD Section 4.4
quantize_inr = quantize_paisa


def get_imt_metal_depreciation_rate(vehicle_age_years: float) -> Decimal:
    """
    Statutory age-based depreciation schedule for sheet metal parts under IMT:
      Age < 6 months (< 0.5 yr): 0%
      6 months to 1 year (0.5 to 1.0 yr): 5%
      1 to 2 years (1.0 to 2.0 yr): 10%
      2 to 3 years (2.0 to 3.0 yr): 15%
      3 to 4 years (3.0 to 4.0 yr): 25%
      4 to 5 years (4.0 to 5.0 yr): 35%
      5 to 10 years (5.0 to 10.0 yr): 40%
      > 10 years (> 10.0 yr): 50%
    """
    if vehicle_age_years < 0.5:
        return Decimal("0.00")
    elif vehicle_age_years <= 1.0:
        return Decimal("0.05")
    elif vehicle_age_years <= 2.0:
        return Decimal("0.10")
    elif vehicle_age_years <= 3.0:
        return Decimal("0.15")
    elif vehicle_age_years <= 4.0:
        return Decimal("0.25")
    elif vehicle_age_years <= 5.0:
        return Decimal("0.35")
    elif vehicle_age_years <= 10.0:
        return Decimal("0.40")
    else:
        return Decimal("0.50")


def calculate_depreciation_rate(
    material: MaterialType | str,
    vehicle_age_years: float,
    is_zero_dep: bool = False,
) -> Decimal:
    """Compute statutory depreciation rate for a replacement part under IMT."""
    if is_zero_dep:
        return Decimal("0.00")

    if isinstance(material, str):
        try:
            mat = MaterialType(material.lower())
        except ValueError:
            mat = MaterialType.METAL
    else:
        mat = material

    if mat == MaterialType.GLASS:
        return Decimal("0.00")
    elif mat in (MaterialType.PLASTIC, MaterialType.RUBBER):
        return Decimal("0.50")
    elif mat == MaterialType.FIBERGLASS:
        return Decimal("0.30")
    elif mat in (MaterialType.METAL, MaterialType.ASSEMBLY):
        return get_imt_metal_depreciation_rate(vehicle_age_years)
    return Decimal("0.00")


# Alias per LLD Section 4.4
get_part_depreciation_rate = calculate_depreciation_rate


def evaluate_repair_action(
    is_repairable: bool,
    depth_grade: str | Any,
    iop_ratio: float,
) -> RepairAction:
    """
    Deterministic repair vs replace rule:
    Action = REPLACE if not is_repairable OR depth_grade == L5_STRUCTURAL_TEAR OR iop_ratio > 0.40
    Action = REPAIR otherwise.
    """
    if not is_repairable:
        return RepairAction.REPLACE
    dg_str = depth_grade.value if hasattr(depth_grade, "value") else str(depth_grade)
    if dg_str == "L5_STRUCTURAL_TEAR":
        return RepairAction.REPLACE
    if iop_ratio > 0.40:
        return RepairAction.REPLACE
    return RepairAction.REPAIR


# Alias per LLD Section 4.4
determine_repair_action = evaluate_repair_action


def calculate_dent_labor_multiplier(iop_ratio: float) -> Decimal:
    """Continuous denting labor scaling: gamma(IoP) = min(2.0, 1.0 + IoP * 2.5)."""
    clamped_iop = max(Decimal("0.0"), min(Decimal("1.0"), Decimal(str(iop_ratio))))
    val = Decimal("1.0") + (clamped_iop * Decimal("2.5"))
    multiplier = min(Decimal("2.0"), val)
    return quantize_paisa(multiplier)


# Alias per LLD Section 4.4
calculate_denting_labor_multiplier = calculate_dent_labor_multiplier


def get_paint_finish_multiplier(paint_type: PaintType | str) -> Decimal:
    """Return factory finish paint multiplier."""
    if isinstance(paint_type, str):
        try:
            pt = PaintType(paint_type.lower())
        except ValueError:
            pt = PaintType.SOLID
    else:
        pt = paint_type

    multipliers = {
        PaintType.SOLID: Decimal("1.00"),
        PaintType.METALLIC: Decimal("1.15"),
        PaintType.PEARL: Decimal("1.30"),
        PaintType.MATTE: Decimal("1.35"),
    }
    return multipliers.get(pt, Decimal("1.00"))


# Alias per LLD Section 4.4
get_paint_type_multiplier = get_paint_finish_multiplier


def get_salvage_deduction_rate(
    material: MaterialType | str,
    action: RepairAction | str,
) -> Decimal:
    """Statutory salvage deduction percentage on replaced parts."""
    act_str = action.value if hasattr(action, "value") else str(action).upper()
    if act_str == RepairAction.REPAIR.value:
        return Decimal("0.00")

    if isinstance(material, str):
        try:
            mat = MaterialType(material.lower())
        except ValueError:
            mat = MaterialType.METAL
    else:
        mat = material

    if mat == MaterialType.METAL:
        return Decimal("0.05")
    elif mat in (MaterialType.PLASTIC, MaterialType.RUBBER):
        return Decimal("0.02")
    return Decimal("0.00")


def calculate_salvage_deduction(
    material: MaterialType | str,
    action: RepairAction | str,
    net_part_cost_inr: Optional[Decimal] = None,
) -> Decimal:
    """
    Calculate statutory salvage deduction.
    If net_part_cost_inr is provided, returns quantized monetary deduction in INR.
    Otherwise, returns the statutory salvage rate (e.g. Decimal('0.05')).
    """
    rate = get_salvage_deduction_rate(material, action)
    if net_part_cost_inr is not None:
        return quantize_paisa(net_part_cost_inr * rate)
    return rate


def get_compulsory_excess_by_cc(engine_cc: Optional[int]) -> Decimal:
    """
    Statutory compulsory excess under the Indian Motor Tariff:
    - Displacement <= 1500cc (or unspecified): ₹1,000.00
    - Displacement > 1500cc: ₹2,000.00
    """
    if engine_cc is not None and engine_cc > 1500:
        return Decimal("2000.00")
    return Decimal("1000.00")


def calculate_consumables_allowance(
    base_parts_or_repair_inr: Decimal,
    has_consumables_addon: bool = True,
    allowance_rate: Decimal = Decimal("0.05"),
) -> Decimal:
    """
    Calculate statutory / policy consumables allowance (fasteners, clips, lubricants, oils).
    Defaults to 5% of base if consumables cover is active; 0.00 if inactive.
    """
    if not has_consumables_addon:
        return Decimal("0.00")
    return quantize_paisa(base_parts_or_repair_inr * allowance_rate)


def resolve_paint_overlap_factors(
    panel_items: List[Tuple[str, Decimal]],
) -> List[Tuple[str, Decimal]]:
    """
    Sort panels requiring paint by base paint cost DESC.
    First panel receives 1.00x factor; subsequent panels receive 0.80x (20% overlap discount).
    """
    sorted_items = sorted(panel_items, key=lambda x: x[1], reverse=True)
    results = []
    for idx, (key, _) in enumerate(sorted_items):
        factor = Decimal("1.00") if idx == 0 else OVERLAP_DISCOUNT_FACTOR
        results.append((key, factor))
    return results
