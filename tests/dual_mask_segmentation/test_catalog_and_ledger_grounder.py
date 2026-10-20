"""
tests/dual_mask_segmentation/test_catalog_and_ledger_grounder.py
Verifies PostgreSQL OEM catalogue grounding and Stage 2 Guardrail Escalations:
- T2-10: Repeat claim on unrepaired part triggers Stage2UnrepairedRepeatError (ESC-03)
- T2-11: Opposite-side multi-hit triggers Stage2OppositeSideMultiHitError (ESC-05)
- T2-12: Safety-critical part or damage triggers Stage2SafetyCriticalError (ESC-06)
- T2-13: Zero damage or low confidence (<0.45) triggers Stage2LowConfidenceOrNoDamageError (ESC-07)
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dual_mask_segmentation.catalog_and_ledger_grounder import (
    CatalogAndLedgerGrounder,
)
from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.exceptions import (
    Stage2LowConfidenceOrNoDamageError,
    Stage2OppositeSideMultiHitError,
    Stage2SafetyCriticalError,
    Stage2UnrepairedRepeatError,
)
from app.domain.dual_mask_segmentation.schemas import Stage2FailureCode
from tests.dual_mask_segmentation.conftest import make_test_candidate


class TestCatalogAndLedgerGrounder:
    @pytest.fixture
    def grounder(
        self, db_session: AsyncSession, stage2_settings: Stage2Settings
    ) -> CatalogAndLedgerGrounder:
        return CatalogAndLedgerGrounder(db_session=db_session, settings=stage2_settings)

    @pytest.mark.asyncio
    async def test_t2_10_unrepaired_repeat_claim_triggers_esc_03(
        self, grounder: CatalogAndLedgerGrounder
    ):
        """T2-10: Prior cash-in-lieu settlement exists on 'back_bumper' for policy vehicle
        MH12DE1433 in unrepaired_claims_ledger without repair verification.
        Submitting a new claim on back_bumper MUST trigger Stage2UnrepairedRepeatError (ESC-03).
        """
        candidate = make_test_candidate(
            canonical_part_key="back_bumper",
            damage_classes=["dent"],
            part_confidence=0.91,
            damage_confidence=0.87,
        )

        with pytest.raises(Stage2UnrepairedRepeatError) as exc_info:
            await grounder.ground_and_check_guardrails("POL-HAPPY-001", [candidate])

        err = exc_info.value
        assert err.escalation_code == "ESC-03"
        assert Stage2FailureCode.S2_UNREPAIRED_REPEAT_CLAIM.value in err.failure_codes
        assert "Prior unrepaired cash-in-lieu settlement exists" in err.message
        assert "back_bumper" in err.message

    @pytest.mark.asyncio
    async def test_t2_11_opposite_side_multi_hit_triggers_esc_05(
        self, grounder: CatalogAndLedgerGrounder
    ):
        """T2-11: Opposite-side multi-hit detection:
        Claiming simultaneous damage on both left-side ('front_left_door') and
        right-side ('back_right_door') vehicle body panels in a single incident
        triggers Stage2OppositeSideMultiHitError (ESC-05) for combined multi-incident escalation.
        """
        left_cand = make_test_candidate(
            canonical_part_key="front_left_door",
            damage_classes=["dent"],
            part_confidence=0.93,
            damage_confidence=0.88,
        )
        right_cand = make_test_candidate(
            canonical_part_key="back_right_door",
            damage_classes=["scratch"],
            part_confidence=0.90,
            damage_confidence=0.85,
        )

        with pytest.raises(Stage2OppositeSideMultiHitError) as exc_info:
            await grounder.ground_and_check_guardrails("POL-HAPPY-001", [left_cand, right_cand])

        err = exc_info.value
        assert err.escalation_code == "ESC-05"
        assert Stage2FailureCode.S2_OPPOSITE_SIDE_MULTI_HIT.value in err.failure_codes
        assert "Opposite-side multi-hit detected" in err.message

    @pytest.mark.asyncio
    async def test_t2_12_safety_critical_part_and_damage_trigger_esc_06(
        self, grounder: CatalogAndLedgerGrounder
    ):
        """T2-12: Safety-critical parts ('front_glass', 'wheel') or structural damage classes
        ('glass_shatter', 'tire_flat') trigger Stage2SafetyCriticalError (ESC-06), routing
        the claim to a physical garage inspection.
        """
        # Case A: Safety-critical canonical part 'front_glass'
        glass_cand = make_test_candidate(
            canonical_part_key="front_glass",
            damage_classes=["crack"],
            part_confidence=0.92,
            damage_confidence=0.89,
        )
        with pytest.raises(Stage2SafetyCriticalError) as exc_a:
            await grounder.ground_and_check_guardrails("POL-HAPPY-001", [glass_cand])
        assert exc_a.value.escalation_code == "ESC-06"
        assert Stage2FailureCode.S2_SAFETY_CRITICAL_PART_DAMAGED.value in exc_a.value.failure_codes

        # Case B: Safety-critical canonical part 'wheel'
        wheel_cand = make_test_candidate(
            canonical_part_key="wheel",
            damage_classes=["scratch"],
            part_confidence=0.94,
            damage_confidence=0.86,
        )
        with pytest.raises(Stage2SafetyCriticalError) as exc_b:
            await grounder.ground_and_check_guardrails("POL-HAPPY-001", [wheel_cand])
        assert exc_b.value.escalation_code == "ESC-06"

        # Case C: Safety-critical damage class 'glass_shatter' on a normal body panel
        shatter_cand = make_test_candidate(
            canonical_part_key="front_left_door",
            damage_classes=["glass_shatter"],
            part_confidence=0.91,
            damage_confidence=0.90,
        )
        with pytest.raises(Stage2SafetyCriticalError) as exc_c:
            await grounder.ground_and_check_guardrails("POL-HAPPY-001", [shatter_cand])
        assert exc_c.value.escalation_code == "ESC-06"

        # Case D: Safety-critical damage class 'tire_flat'
        tire_cand = make_test_candidate(
            canonical_part_key="front_left_door",
            damage_classes=["tire_flat"],
            part_confidence=0.91,
            damage_confidence=0.90,
        )
        with pytest.raises(Stage2SafetyCriticalError) as exc_d:
            await grounder.ground_and_check_guardrails("POL-HAPPY-001", [tire_cand])
        assert exc_d.value.escalation_code == "ESC-06"

    @pytest.mark.asyncio
    async def test_t2_13_zero_damage_or_low_confidence_triggers_esc_07(
        self, grounder: CatalogAndLedgerGrounder
    ):
        """T2-13: When zero damage candidates survive persistence/filtering, or when segmentation
        confidence falls below 0.45, Stage2LowConfidenceOrNoDamageError (ESC-07) is triggered.
        """
        # Case A: Zero surviving candidates (e.g. pristine vehicle or all spillovers rejected)
        with pytest.raises(Stage2LowConfidenceOrNoDamageError) as exc_zero:
            await grounder.ground_and_check_guardrails("POL-HAPPY-001", [])
        assert exc_zero.value.escalation_code == "ESC-07"
        assert Stage2FailureCode.S2_NO_DAMAGE_DETECTED.value in exc_zero.value.failure_codes

        # Case B: Part segmentation confidence below 0.45 floor (e.g. 0.40)
        low_part_cand = make_test_candidate(
            canonical_part_key="front_left_door",
            damage_classes=["dent"],
            part_confidence=0.40,
            damage_confidence=0.88,
        )
        with pytest.raises(Stage2LowConfidenceOrNoDamageError) as exc_low_p:
            await grounder.ground_and_check_guardrails("POL-HAPPY-001", [low_part_cand])
        assert exc_low_p.value.escalation_code == "ESC-07"
        assert Stage2FailureCode.S2_LOW_SEGMENTATION_CONFIDENCE.value in exc_low_p.value.failure_codes

        # Case C: Damage segmentation confidence below 0.45 floor (e.g. 0.42)
        low_dmg_cand = make_test_candidate(
            canonical_part_key="front_left_door",
            damage_classes=["dent"],
            part_confidence=0.89,
            damage_confidence=0.42,
        )
        with pytest.raises(Stage2LowConfidenceOrNoDamageError) as exc_low_d:
            await grounder.ground_and_check_guardrails("POL-HAPPY-001", [low_dmg_cand])
        assert exc_low_d.value.escalation_code == "ESC-07"
        assert Stage2FailureCode.S2_LOW_SEGMENTATION_CONFIDENCE.value in exc_low_d.value.failure_codes
