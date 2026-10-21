"""
tests/actuarial_pricing/test_rules.py
Unit tests for pure deterministic actuarial rules and mathematical scaling functions.
"""
from decimal import Decimal
import pytest

from app.domain.actuarial_pricing.enums import (
    MaterialType,
    PaintType,
    RepairAction,
)
from app.domain.actuarial_pricing.rules import (
    calculate_consumables_allowance,
    calculate_dent_labor_multiplier,
    calculate_denting_labor_multiplier,
    calculate_depreciation_rate,
    calculate_salvage_deduction,
    determine_repair_action,
    evaluate_repair_action,
    get_compulsory_excess_by_cc,
    get_imt_metal_depreciation_rate,
    get_paint_finish_multiplier,
    get_paint_type_multiplier,
    get_part_depreciation_rate,
    get_salvage_deduction_rate,
    quantize_inr,
    quantize_paisa,
    resolve_paint_overlap_factors,
)
from app.domain.vlm_damage_inspection.schemas import DepthGrade


class TestPaisaQuantization:
    """Tests for paisa quantization and half-up rounding precision."""

    def test_quantize_paisa_half_up(self):
        assert quantize_paisa(Decimal("10.005")) == Decimal("10.01")
        assert quantize_paisa(Decimal("10.004")) == Decimal("10.00")
        assert quantize_paisa(Decimal("10.015")) == Decimal("10.02")
        assert quantize_paisa(Decimal("10.025")) == Decimal("10.03")

    def test_quantize_paisa_types(self):
        assert quantize_paisa(10) == Decimal("10.00")
        assert quantize_paisa("123.456") == Decimal("123.46")
        assert quantize_paisa(12.345) == Decimal("12.35")
        assert quantize_paisa(0) == Decimal("0.00")

    def test_quantize_inr_alias(self):
        assert quantize_inr(Decimal("25000.004")) == Decimal("25000.00")
        assert quantize_inr(Decimal("25000.005")) == Decimal("25000.01")


class TestImtMetalDepreciationSchedule:
    """Tests for all 8 statutory age-based depreciation brackets for sheet metal."""

    @pytest.mark.parametrize(
        "age_years,expected_rate",
        [
            # Bracket 1: < 6 months (0.0 to < 0.5 yr) -> 0%
            (0.0, Decimal("0.00")),
            (0.2, Decimal("0.00")),
            (0.499, Decimal("0.00")),
            # Bracket 2: 6 months to 1 year (0.5 to 1.0 yr) -> 5%
            (0.5, Decimal("0.05")),
            (0.75, Decimal("0.05")),
            (1.0, Decimal("0.05")),
            # Bracket 3: 1 to 2 years (1.0 to 2.0 yr) -> 10%
            (1.01, Decimal("0.10")),
            (1.5, Decimal("0.10")),
            (2.0, Decimal("0.10")),
            # Bracket 4: 2 to 3 years (2.0 to 3.0 yr) -> 15%
            (2.01, Decimal("0.15")),
            (2.5, Decimal("0.15")),
            (3.0, Decimal("0.15")),
            # Bracket 5: 3 to 4 years (3.0 to 4.0 yr) -> 25%
            (3.01, Decimal("0.25")),
            (3.5, Decimal("0.25")),
            (4.0, Decimal("0.25")),
            # Bracket 6: 4 to 5 years (4.0 to 5.0 yr) -> 35%
            (4.01, Decimal("0.35")),
            (4.5, Decimal("0.35")),
            (5.0, Decimal("0.35")),
            # Bracket 7: 5 to 10 years (5.0 to 10.0 yr) -> 40%
            (5.01, Decimal("0.40")),
            (7.5, Decimal("0.40")),
            (10.0, Decimal("0.40")),
            # Bracket 8: > 10 years (> 10.0 yr) -> 50%
            (10.01, Decimal("0.50")),
            (12.0, Decimal("0.50")),
            (25.0, Decimal("0.50")),
        ],
    )
    def test_all_eight_metal_depreciation_brackets(self, age_years: float, expected_rate: Decimal):
        assert get_imt_metal_depreciation_rate(age_years) == expected_rate


class TestMaterialDepreciationRules:
    """Tests for material-specific depreciation rates under IMT and Zero-Dep rider."""

    def test_zero_depreciation_rider_active(self):
        # Under zero-dep, all materials regardless of age have 0% depreciation
        for mat in [
            MaterialType.METAL,
            MaterialType.PLASTIC,
            MaterialType.RUBBER,
            MaterialType.GLASS,
            MaterialType.FIBERGLASS,
            MaterialType.ASSEMBLY,
        ]:
            for age in [0.2, 2.0, 4.5, 12.0]:
                assert calculate_depreciation_rate(mat, age, is_zero_dep=True) == Decimal("0.00")

    def test_glass_statutory_depreciation_zero(self):
        # Glass never depreciates under IMT
        assert calculate_depreciation_rate(MaterialType.GLASS, 0.2) == Decimal("0.00")
        assert calculate_depreciation_rate(MaterialType.GLASS, 4.0) == Decimal("0.00")
        assert calculate_depreciation_rate(MaterialType.GLASS, 12.0) == Decimal("0.00")
        assert calculate_depreciation_rate("glass", 5.0) == Decimal("0.00")

    def test_plastic_and_rubber_flat_50_percent(self):
        # Plastic and rubber suffer flat 50% statutory depreciation
        assert calculate_depreciation_rate(MaterialType.PLASTIC, 0.2) == Decimal("0.50")
        assert calculate_depreciation_rate(MaterialType.PLASTIC, 6.0) == Decimal("0.50")
        assert calculate_depreciation_rate(MaterialType.RUBBER, 0.5) == Decimal("0.50")
        assert calculate_depreciation_rate("rubber", 8.0) == Decimal("0.50")

    def test_fiberglass_flat_30_percent(self):
        # Fiberglass suffers flat 30% statutory depreciation
        assert calculate_depreciation_rate(MaterialType.FIBERGLASS, 0.1) == Decimal("0.30")
        assert calculate_depreciation_rate(MaterialType.FIBERGLASS, 5.0) == Decimal("0.30")
        assert calculate_depreciation_rate("fiberglass", 10.0) == Decimal("0.30")

    def test_metal_and_assembly_follow_age_schedule(self):
        # Metal and assemblies follow statutory age brackets
        assert calculate_depreciation_rate(MaterialType.METAL, 0.3) == Decimal("0.00")
        assert calculate_depreciation_rate(MaterialType.METAL, 4.0) == Decimal("0.25")
        assert calculate_depreciation_rate(MaterialType.ASSEMBLY, 4.0) == Decimal("0.25")
        assert calculate_depreciation_rate(MaterialType.ASSEMBLY, 11.0) == Decimal("0.50")

    def test_alias_and_string_case_insensitivity(self):
        assert get_part_depreciation_rate("PLASTIC", 2.0) == Decimal("0.50")
        assert get_part_depreciation_rate("Rubber", 1.0) == Decimal("0.50")
        assert get_part_depreciation_rate("unknown_material", 4.0) == Decimal("0.25")  # fallback to metal
        assert calculate_depreciation_rate(MaterialType.METAL, 4.0) == Decimal("0.25")
        # Dummy unhandled type for branch coverage
        assert calculate_depreciation_rate(None, 4.0) == Decimal("0.00")


class TestRepairActionDetermination:
    """Tests for deterministic REPAIR vs REPLACE decision logic."""

    def test_unrepairable_part_always_replaced(self):
        # Even minor scuff on unrepairable part must be replaced
        assert evaluate_repair_action(
            is_repairable=False,
            depth_grade=DepthGrade.L1_SURFACE_SCUFF,
            iop_ratio=0.01,
        ) == RepairAction.REPLACE

    def test_structural_tear_always_replaced(self):
        # L5 structural tear must be replaced even with low IoP
        assert evaluate_repair_action(
            is_repairable=True,
            depth_grade=DepthGrade.L5_STRUCTURAL_TEAR,
            iop_ratio=0.05,
        ) == RepairAction.REPLACE
        assert evaluate_repair_action(
            is_repairable=True,
            depth_grade="L5_STRUCTURAL_TEAR",
            iop_ratio=0.02,
        ) == RepairAction.REPLACE

    def test_iop_exceeding_threshold_triggers_replacement(self):
        # IoP > 0.40 triggers replacement
        assert evaluate_repair_action(
            is_repairable=True,
            depth_grade=DepthGrade.L4_CREASED_DENT,
            iop_ratio=0.45,
        ) == RepairAction.REPLACE
        assert evaluate_repair_action(
            is_repairable=True,
            depth_grade=DepthGrade.L2_BASECOAT_SCRATCH,
            iop_ratio=0.4001,
        ) == RepairAction.REPLACE

    def test_iop_at_or_below_threshold_repaired(self):
        # IoP <= 0.40 on repairable panel without L5 tear -> REPAIR
        assert evaluate_repair_action(
            is_repairable=True,
            depth_grade=DepthGrade.L4_CREASED_DENT,
            iop_ratio=0.40,
        ) == RepairAction.REPAIR
        assert evaluate_repair_action(
            is_repairable=True,
            depth_grade=DepthGrade.L3_SHALLOW_DENT_PDR,
            iop_ratio=0.15,
        ) == RepairAction.REPAIR
        assert evaluate_repair_action(
            is_repairable=True,
            depth_grade=DepthGrade.L1_SURFACE_SCUFF,
            iop_ratio=0.05,
        ) == RepairAction.REPAIR

    def test_alias_determine_repair_action(self):
        assert determine_repair_action(True, "L1_SURFACE_SCUFF", 0.05) == RepairAction.REPAIR
        assert determine_repair_action(False, "L1_SURFACE_SCUFF", 0.05) == RepairAction.REPLACE


class TestDentLaborMultiplier:
    """Tests for continuous dent labor scaling formula gamma(IoP) = min(2.0, 1.0 + IoP * 2.5)."""

    def test_zero_or_negative_iop(self):
        assert calculate_dent_labor_multiplier(0.0) == Decimal("1.00")
        assert calculate_dent_labor_multiplier(-0.1) == Decimal("1.00")

    def test_moderate_iop_scaling(self):
        # IoP = 0.10 -> 1.0 + 0.25 = 1.25
        assert calculate_dent_labor_multiplier(0.10) == Decimal("1.25")
        # IoP = 0.15 -> 1.0 + 0.375 = 1.375 -> rounded half up to 1.38
        assert calculate_dent_labor_multiplier(0.15) == Decimal("1.38")
        # IoP = 0.20 -> 1.0 + 0.50 = 1.50
        assert calculate_dent_labor_multiplier(0.20) == Decimal("1.50")
        # IoP = 0.35 -> 1.0 + 0.875 = 1.875 -> rounded half up to 1.88
        assert calculate_dent_labor_multiplier(0.35) == Decimal("1.88")

    def test_cap_at_two(self):
        # IoP = 0.40 -> 1.0 + 1.00 = 2.00
        assert calculate_dent_labor_multiplier(0.40) == Decimal("2.00")
        # IoP > 0.40 capped at 2.00
        assert calculate_dent_labor_multiplier(0.50) == Decimal("2.00")
        assert calculate_dent_labor_multiplier(1.0) == Decimal("2.00")
        assert calculate_dent_labor_multiplier(2.0) == Decimal("2.00")

    def test_alias_calculate_denting_labor_multiplier(self):
        assert calculate_denting_labor_multiplier(0.10) == Decimal("1.25")


class TestPaintFinishMultipliers:
    """Tests for paint type multipliers."""

    def test_paint_finish_rates(self):
        assert get_paint_finish_multiplier(PaintType.SOLID) == Decimal("1.00")
        assert get_paint_finish_multiplier(PaintType.METALLIC) == Decimal("1.15")
        assert get_paint_finish_multiplier(PaintType.PEARL) == Decimal("1.30")
        assert get_paint_finish_multiplier(PaintType.MATTE) == Decimal("1.35")
        assert get_paint_finish_multiplier(None) == Decimal("1.00")

    def test_paint_finish_strings_and_fallbacks(self):
        assert get_paint_finish_multiplier("solid") == Decimal("1.00")
        assert get_paint_finish_multiplier("METALLIC") == Decimal("1.15")
        assert get_paint_finish_multiplier("pearl") == Decimal("1.30")
        assert get_paint_finish_multiplier("matte") == Decimal("1.35")
        assert get_paint_finish_multiplier("neon_glow") == Decimal("1.00")

    def test_alias_get_paint_type_multiplier(self):
        assert get_paint_type_multiplier(PaintType.METALLIC) == Decimal("1.15")


class TestSalvageScrapRules:
    """Tests for statutory salvage deduction percentages and calculations."""

    def test_repair_salvage_is_zero(self):
        # No salvage deduction on repaired parts
        for mat in [MaterialType.METAL, MaterialType.PLASTIC, MaterialType.GLASS]:
            assert get_salvage_deduction_rate(mat, RepairAction.REPAIR) == Decimal("0.00")
            assert calculate_salvage_deduction(mat, RepairAction.REPAIR, Decimal("10000.00")) == Decimal("0.00")

    def test_replaced_part_salvage_rates(self):
        # Metal replacement: 5%
        assert get_salvage_deduction_rate(MaterialType.METAL, RepairAction.REPLACE) == Decimal("0.05")
        # Plastic/Rubber replacement: 2%
        assert get_salvage_deduction_rate(MaterialType.PLASTIC, RepairAction.REPLACE) == Decimal("0.02")
        assert get_salvage_deduction_rate(MaterialType.RUBBER, RepairAction.REPLACE) == Decimal("0.02")
        # Glass/Fiberglass replacement: 0%
        assert get_salvage_deduction_rate(MaterialType.GLASS, RepairAction.REPLACE) == Decimal("0.00")
        assert get_salvage_deduction_rate(MaterialType.FIBERGLASS, RepairAction.REPLACE) == Decimal("0.00")

    def test_calculate_salvage_monetary_amount(self):
        # 5% of ₹8,625.00 = ₹431.25
        assert calculate_salvage_deduction(
            MaterialType.METAL, RepairAction.REPLACE, Decimal("8625.00")
        ) == Decimal("431.25")
        # 2% of ₹4,100.00 = ₹82.00
        assert calculate_salvage_deduction(
            MaterialType.PLASTIC, RepairAction.REPLACE, Decimal("4100.00")
        ) == Decimal("82.00")
        # Without net_part_cost_inr returns the rate directly
        assert calculate_salvage_deduction(MaterialType.METAL, RepairAction.REPLACE) == Decimal("0.05")
        # Invalid material string in salvage deduction
        assert get_salvage_deduction_rate("invalid_mat", RepairAction.REPLACE) == Decimal("0.05")  # fallback to METAL (0.05)


class TestCompulsoryExcessByCc:
    """Tests for engine displacement compulsory deductible."""

    def test_compulsory_excess(self):
        assert get_compulsory_excess_by_cc(None) == Decimal("1000.00")
        assert get_compulsory_excess_by_cc(1197) == Decimal("1000.00")
        assert get_compulsory_excess_by_cc(1500) == Decimal("1000.00")
        assert get_compulsory_excess_by_cc(1501) == Decimal("2000.00")
        assert get_compulsory_excess_by_cc(2755) == Decimal("2000.00")


class TestConsumablesAllowance:
    """Tests for consumables allowance calculation."""

    def test_consumables_addon_active(self):
        # 5% of base ₹10,000.00 is ₹500.00
        assert calculate_consumables_allowance(Decimal("10000.00"), has_consumables_addon=True) == Decimal("500.00")
        # Inactive cover gives ₹0.00
        assert calculate_consumables_allowance(Decimal("10000.00"), has_consumables_addon=False) == Decimal("0.00")


class TestPaintOverlapScheduling:
    """Tests for adjacent panel paint overlap discount resolution."""

    def test_empty_panel_list(self):
        assert resolve_paint_overlap_factors([]) == []

    def test_single_panel_full_rate(self):
        res = resolve_paint_overlap_factors([("front_left_door", Decimal("4200.00"))])
        assert res == [("front_left_door", Decimal("1.00"))]

    def test_multi_panel_overlap_sorting(self):
        # Items provided out of order:
        # bumper (3800), door (4200), fender (3200)
        items = [
            ("front_bumper", Decimal("3800.00")),
            ("front_left_door", Decimal("4200.00")),
            ("front_left_fender", Decimal("3200.00")),
        ]
        res = resolve_paint_overlap_factors(items)
        # Door is highest -> 1.00 factor; bumper and fender receive 0.80 factor
        assert res == [
            ("front_left_door", Decimal("1.00")),
            ("front_bumper", Decimal("0.80")),
            ("front_left_fender", Decimal("0.80")),
        ]
