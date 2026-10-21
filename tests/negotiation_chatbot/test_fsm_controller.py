"""
tests/negotiation_chatbot/test_fsm_controller.py
Deterministic unit test suite for Stage 5 Negotiation Chatbot FSM controller.
"""
from decimal import Decimal
import pytest
from app.domain.actuarial_pricing.schemas import CashSettlementBandDTO
from app.domain.negotiation_chatbot.fsm_controller import NegotiationFSMController
from app.domain.negotiation_chatbot.schemas import ClaimantIntent, NegotiationRoundState


@pytest.fixture
def standard_band() -> CashSettlementBandDTO:
    """
    Standard settlement band fixture based on net claim liability ₹10,000.00:
    - Initial offer (Round 0): 75% = ₹7,500.00
    - Target settlement (Round 1 cap): 85% = ₹8,500.00
    - Walk-away cap (Round 2 cap & Round 3 lock): 95% = ₹9,500.00 (<= ₹25,000.00)
    """
    return CashSettlementBandDTO(
        initial_offer_inr=Decimal("7500.00"),
        target_settlement_inr=Decimal("8500.00"),
        walkaway_cap_inr=Decimal("9500.00"),
        financial_ceiling_inr=Decimal("25000.00"),
    )


@pytest.fixture
def controller() -> NegotiationFSMController:
    return NegotiationFSMController()


def test_round_0_initial_offer(standard_band):
    """Verifies that the initial offer band matches 75% of net liability."""
    assert standard_band.initial_offer_inr == Decimal("7500.00")
    assert standard_band.target_settlement_inr == Decimal("8500.00")
    assert standard_band.walkaway_cap_inr == Decimal("9500.00")


@pytest.mark.parametrize(
    "rationale_score,expected_offer",
    [
        (0.50, Decimal("8000.00")),  # 7500 + 0.50 * (8500 - 7500) = 8000
        (0.35, Decimal("7850.00")),  # 7500 + 0.35 * (8500 - 7500) = 7850
        (0.25, Decimal("7750.00")),  # 7500 + 0.25 * (8500 - 7500) = 7750
    ],
)
def test_round_1_concession_math_dynamic_alpha(controller, standard_band, rationale_score, expected_offer):
    """
    Verifies Round 1 concession math: O_1 <= O_target with dynamic alpha values:
    - 0.50 for technical rationale
    - 0.35 for Hinglish / expensive claim
    - 0.25 for baseline negotiation
    """
    next_round, next_offer, round_state, is_terminal, reason = controller.compute_next_offer(
        current_round=0,
        current_offer_inr=standard_band.initial_offer_inr,
        settlement_band=standard_band,
        intent=ClaimantIntent.COUNTER,
        claimant_counteroffer_inr=Decimal("9000.00"),  # Demand clamped to 8500 round 1 cap
        rationale_score=rationale_score,
    )

    assert next_round == 1
    assert next_offer == expected_offer
    assert next_offer <= standard_band.target_settlement_inr
    assert round_state == NegotiationRoundState.ROUND_1_COUNTER
    assert is_terminal is False
    assert f"alpha={rationale_score:.2f}" in reason


def test_round_2_concession_math(controller, standard_band):
    """
    Verifies Round 2 concession math: O_2 <= O_max (95% <= ₹25,000).
    Moves from Round 1 offer (₹8,000) toward Round 2 cap (₹9,500).
    """
    current_offer = Decimal("8000.00")
    counteroffer = Decimal("10000.00")  # Exceeds walkaway cap (9500)
    alpha = 0.50

    next_round, next_offer, round_state, is_terminal, reason = controller.compute_next_offer(
        current_round=1,
        current_offer_inr=current_offer,
        settlement_band=standard_band,
        intent=ClaimantIntent.COUNTER,
        claimant_counteroffer_inr=counteroffer,
        rationale_score=alpha,
    )

    assert next_round == 2
    assert next_offer == Decimal("8750.00")
    assert next_offer <= standard_band.walkaway_cap_inr
    assert round_state == NegotiationRoundState.ROUND_2_COUNTER
    assert is_terminal is False


def test_round_3_terminal_lock(controller, standard_band):
    """
    Verifies that transitioning to Round 3 locks the offer at O_max with is_terminal=True.
    Further attempts to compute offers beyond Round 3 maintain the terminal lock.
    """
    current_offer = Decimal("8750.00")
    next_round, next_offer, round_state, is_terminal, reason = controller.compute_next_offer(
        current_round=2,
        current_offer_inr=current_offer,
        settlement_band=standard_band,
        intent=ClaimantIntent.COUNTER,
        claimant_counteroffer_inr=Decimal("12000.00"),
        rationale_score=0.50,
    )

    assert next_round == 3
    assert next_offer == standard_band.walkaway_cap_inr
    assert round_state == NegotiationRoundState.ROUND_3_FINAL
    assert is_terminal is True
    assert "Final round reached" in reason

    # Calling when current_round >= 3 immediately returns terminal lock
    r3, off3, st3, term3, rsn3 = controller.compute_next_offer(
        current_round=3,
        current_offer_inr=standard_band.walkaway_cap_inr,
        settlement_band=standard_band,
        intent=ClaimantIntent.COUNTER,
        claimant_counteroffer_inr=Decimal("15000.00"),
        rationale_score=0.50,
    )
    assert r3 == 3
    assert off3 == standard_band.walkaway_cap_inr
    assert st3 == NegotiationRoundState.ROUND_3_FINAL
    assert term3 is True


def test_anchor_inversion_guard(controller, standard_band):
    """
    Verifies Anchor Inversion Guard:
    When claimant submits a counteroffer lower than or equal to current offer,
    the current offer is maintained, no decrement occurs, and explanation is returned.
    """
    current_offer = Decimal("7500.00")
    lower_counteroffer = Decimal("7000.00")

    next_round, next_offer, round_state, is_terminal, reason = controller.compute_next_offer(
        current_round=0,
        current_offer_inr=current_offer,
        settlement_band=standard_band,
        intent=ClaimantIntent.COUNTER,
        claimant_counteroffer_inr=lower_counteroffer,
        rationale_score=0.50,
    )

    assert next_round == 1
    assert next_offer == current_offer
    assert is_terminal is False
    assert "lower than current offer" in reason
    assert "Existing offer maintained" in reason


def test_cap_breach_astronomical_counteroffers_clamped(controller, standard_band):
    """
    Verifies that exorbitant counteroffers (e.g. ₹50,000) are clamped to the current round cap
    and cannot breach the target settlement in Round 1 or walkaway cap in Round 2.
    """
    current_offer = Decimal("7500.00")
    astronomical_demand = Decimal("50000.00")

    next_round, next_offer, round_state, is_terminal, reason = controller.compute_next_offer(
        current_round=0,
        current_offer_inr=current_offer,
        settlement_band=standard_band,
        intent=ClaimantIntent.COUNTER,
        claimant_counteroffer_inr=astronomical_demand,
        rationale_score=0.50,
    )

    assert next_offer <= standard_band.target_settlement_inr
    assert next_offer == Decimal("8000.00")


def test_qualitative_plea_without_numbers(controller, standard_band):
    """
    Verifies qualitative plea behavior: when counteroffer_inr is None,
    the FSM applies a soft step (60% toward round cap) scaled by alpha.
    """
    current_offer = Decimal("7500.00")
    next_round, next_offer, round_state, is_terminal, reason = controller.compute_next_offer(
        current_round=0,
        current_offer_inr=current_offer,
        settlement_band=standard_band,
        intent=ClaimantIntent.QUALITATIVE_PLEA,
        claimant_counteroffer_inr=None,
        rationale_score=0.35,
    )

    assert next_round == 1
    assert next_offer == Decimal("7710.00")
    assert next_offer > current_offer
    assert next_offer <= standard_band.target_settlement_inr


def test_monotonic_non_decreasing_invariant(controller, standard_band):
    """
    Verifies the invariant: O_r >= O_{r-1} for all possible user inputs.
    Offers never decrease under any circumstance.
    """
    current_offer = Decimal("8200.00")
    for delta in [-500, 0, 100, 5000]:
        test_demand = current_offer + Decimal(delta) if delta > 0 else Decimal("6000.00")
        _, next_offer, _, _, _ = controller.compute_next_offer(
            current_round=1,
            current_offer_inr=current_offer,
            settlement_band=standard_band,
            intent=ClaimantIntent.COUNTER,
            claimant_counteroffer_inr=test_demand,
            rationale_score=0.25,
        )
        assert next_offer >= current_offer


def test_explicit_accept_and_reject_intents(controller, standard_band):
    """
    Verifies instant terminal states for explicit claimant ACCEPT and REJECT_GARAGE intents.
    """
    current_offer = Decimal("8000.00")

    # Accept
    r_acc, off_acc, st_acc, term_acc, _ = controller.compute_next_offer(
        current_round=1,
        current_offer_inr=current_offer,
        settlement_band=standard_band,
        intent=ClaimantIntent.ACCEPT,
        claimant_counteroffer_inr=None,
        rationale_score=1.0,
    )
    assert st_acc == NegotiationRoundState.SETTLED
    assert off_acc == current_offer
    assert term_acc is True

    # Reject / Garage
    r_rej, off_rej, st_rej, term_rej, _ = controller.compute_next_offer(
        current_round=1,
        current_offer_inr=current_offer,
        settlement_band=standard_band,
        intent=ClaimantIntent.REJECT_GARAGE,
        claimant_counteroffer_inr=None,
        rationale_score=0.0,
    )
    assert st_rej == NegotiationRoundState.REJECTED_GARAGE
    assert off_rej == current_offer
    assert term_rej is True