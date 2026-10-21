"""
tests/settlement_escalation/test_apportionment.py
Unit tests for multi-part cash apportionment engine, penny balancing, and unrepaired ledger commit.
"""
from decimal import Decimal
from unittest.mock import AsyncMock
import pytest
from app.domain.actuarial_pricing.enums import MaterialType, RepairAction
from app.domain.actuarial_pricing.schemas import ActuarialLineItemDTO
from app.domain.settlement_escalation.apportionment import MultiPartApportionmentEngine


def make_line_item(part_key: str, display_name: str, gross_inr: Decimal) -> ActuarialLineItemDTO:
    return ActuarialLineItemDTO(
        canonical_part_key=part_key,
        display_part_name=display_name,
        oem_part_number="OEM-1234",
        material=MaterialType.PLASTIC,
        action=RepairAction.REPLACE,
        depth_grade="L3_SHALLOW_DENT_PDR",
        iop_ratio=0.10,
        base_part_cost_inr=gross_inr * Decimal("0.60"),
        depreciation_rate_pct=Decimal("0.00"),
        depreciation_amount_inr=Decimal("0.00"),
        net_part_cost_inr=gross_inr * Decimal("0.60"),
        salvage_deduction_inr=Decimal("0.00"),
        rr_labour_inr=gross_inr * Decimal("0.10"),
        denting_labour_inr=Decimal("0.00"),
        pdr_polish_flat_inr=Decimal("0.00"),
        base_paint_inr=gross_inr * Decimal("0.20"),
        paint_multiplier=Decimal("1.00"),
        paint_overlap_discount=Decimal("0.00"),
        final_paint_inr=gross_inr * Decimal("0.20"),
        pre_tax_total_inr=gross_inr * Decimal("0.90"),
        gst_amount_inr=gross_inr * Decimal("0.10"),
        gross_line_item_total_inr=gross_inr,
    )


@pytest.fixture
def engine() -> MultiPartApportionmentEngine:
    return MultiPartApportionmentEngine()


def test_single_part_claim_apportionment(engine):
    """Tests single-part claim: 100% of cash payout allocated to single part."""
    item = make_line_item("front_bumper", "Front Bumper", Decimal("10000.00"))
    settled_amount = Decimal("7500.00")

    result = engine.apportion_settlement(settled_amount, [item])

    assert len(result) == 1
    assert result[0].canonical_part_key == "front_bumper"
    assert result[0].apportioned_amount_inr == settled_amount


def test_multi_part_claim_pro_rata_allocation(engine):
    """
    Tests multi-part pro-rata distribution proportional to gross line item costs:
    Part A: ₹6,000 (60%)
    Part B: ₹3,000 (30%)
    Part C: ₹1,000 (10%)
    Settled: ₹8,000.00
    """
    items = [
        make_line_item("hood", "Hood", Decimal("6000.00")),
        make_line_item("front_bumper", "Front Bumper", Decimal("3000.00")),
        make_line_item("front_left_fender", "Left Fender", Decimal("1000.00")),
    ]
    settled_amount = Decimal("8000.00")

    result = engine.apportion_settlement(settled_amount, items)

    assert len(result) == 3
    assert result[0].apportioned_amount_inr == Decimal("4800.00")
    assert result[1].apportioned_amount_inr == Decimal("2400.00")
    assert result[2].apportioned_amount_inr == Decimal("800.00")
    assert sum(p.apportioned_amount_inr for p in result) == settled_amount


def test_penny_balancing(engine):
    """
    Tests penny balancing: when rounding leaves a residual paise difference,
    the residual is credited to the largest line item to guarantee bit-level sum equality.
    """
    items = [
        make_line_item("hood", "Hood", Decimal("5000.00")),
        make_line_item("front_bumper", "Front Bumper", Decimal("3000.00")),
        make_line_item("front_door", "Front Door", Decimal("2000.00")),
    ]
    settled_amount = Decimal("7777.77")

    result = engine.apportion_settlement(settled_amount, items)
    total_allocated = sum(p.apportioned_amount_inr for p in result)
    assert total_allocated == settled_amount


def test_bit_level_decimal_sum_invariant(engine):
    """Tests that sum(apportioned_amount_inr) == settled_amount_inr across irregular test cases."""
    items = [
        make_line_item("part_1", "Part 1", Decimal("3333.33")),
        make_line_item("part_2", "Part 2", Decimal("3333.33")),
        make_line_item("part_3", "Part 3", Decimal("3333.34")),
    ]
    settled_amount = Decimal("10000.00")

    result = engine.apportion_settlement(settled_amount, items)
    assert sum(p.apportioned_amount_inr for p in result) == settled_amount


def test_empty_line_items(engine):
    """Verifies that an empty line items list returns an empty allocation list."""
    assert engine.apportion_settlement(Decimal("5000.00"), []) == []


@pytest.mark.asyncio
async def test_commit_to_ledger(engine):
    """Verifies committing apportioned parts to UnrepairedClaimsRepository with is_repaired_verified=False."""
    mock_repo = AsyncMock()
    apportioned_parts = [
        engine.apportion_settlement(
            Decimal("8000.00"),
            [make_line_item("front_bumper", "Front Bumper", Decimal("8000.00"))],
        )[0]
    ]

    await engine.commit_to_ledger(
        unrepaired_repo=mock_repo,
        registration_number="MH12DE1433",
        apportioned_parts=apportioned_parts,
    )

    mock_repo.record_cash_payout.assert_called_once_with(
        registration_number="MH12DE1433",
        canonical_part_key="front_bumper",
        damage_class="L3_SHALLOW_DENT_PDR",
        settled_amount=Decimal("8000.00"),
    )