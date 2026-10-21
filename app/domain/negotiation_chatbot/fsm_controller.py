"""
app/domain/negotiation_chatbot/fsm_controller.py
Deterministic 3-round concession Finite State Machine with dynamic alpha and anchor inversion guards.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple
from app.domain.actuarial_pricing.schemas import CashSettlementBandDTO
from app.domain.negotiation_chatbot.exceptions import NegotiationRoundExhaustedError
from app.domain.negotiation_chatbot.schemas import (
    ClaimantIntent,
    NegotiationRoundState,
)


class NegotiationFSMController:
    """
    Governs state transitions and mathematical concession steps for Stage 5.
    Pure deterministic Decimal math. Zero LLM authority over financial amounts.
    """

    def compute_next_offer(
        self,
        current_round: int,
        current_offer_inr: Decimal,
        settlement_band: CashSettlementBandDTO,
        intent: ClaimantIntent,
        claimant_counteroffer_inr: Optional[Decimal],
        rationale_score: float,
    ) -> Tuple[int, Decimal, NegotiationRoundState, bool, str]:
        """
        Computes the next round state and offered amount.
        Returns:
            (next_round_num, next_offer_inr, next_state, is_terminal, transition_reason)
        """
        if current_round >= 3:
            # Round 3 is strictly terminal: walk-away cap locked
            return (
                3,
                settlement_band.walkaway_cap_inr,
                NegotiationRoundState.ROUND_3_FINAL,
                True,
                "Walk-away cap reached. Offer is locked at maximum allowable cash payout.",
            )

        next_round = current_round + 1

        # 1. Handle explicit accept
        if intent == ClaimantIntent.ACCEPT:
            return (
                current_round,
                current_offer_inr,
                NegotiationRoundState.SETTLED,
                True,
                "Claimant accepted offer.",
            )

        # 2. Handle cashless garage / surveyor rejection
        if intent == ClaimantIntent.REJECT_GARAGE:
            return (
                current_round,
                current_offer_inr,
                NegotiationRoundState.REJECTED_GARAGE,
                True,
                "Claimant opted for authorized network garage cashless repair.",
            )

        # 3. Determine Round Cap
        if next_round == 1:
            round_cap = settlement_band.target_settlement_inr
            round_state = NegotiationRoundState.ROUND_1_COUNTER
        elif next_round == 2:
            round_cap = settlement_band.walkaway_cap_inr
            round_state = NegotiationRoundState.ROUND_2_COUNTER
        else:
            # Round 3
            return (
                3,
                settlement_band.walkaway_cap_inr,
                NegotiationRoundState.ROUND_3_FINAL,
                True,
                "Final round reached. Offer locked at walk-away cap.",
            )

        # 4. Resolve effective counteroffer amount
        if claimant_counteroffer_inr is not None:
            # Anchor inversion guard
            if claimant_counteroffer_inr <= current_offer_inr:
                return (
                    next_round,
                    current_offer_inr,
                    round_state,
                    False,
                    f"Counteroffer (₹{claimant_counteroffer_inr:,.2f}) is lower than current offer (₹{current_offer_inr:,.2f}). Existing offer maintained.",
                )
            effective_demand = min(claimant_counteroffer_inr, round_cap)
        else:
            # Qualitative plea without number: soft step toward cap
            soft_delta = (round_cap - current_offer_inr) * Decimal("0.60")
            effective_demand = current_offer_inr + soft_delta

        # 5. Apply Concession Formula
        alpha = Decimal(str(rationale_score)).quantize(Decimal("0.01"))
        demand_gap = max(Decimal("0.00"), effective_demand - current_offer_inr)
        concession_step = (alpha * demand_gap).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        calculated_offer = current_offer_inr + concession_step
        next_offer = min(round_cap, calculated_offer).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Guarantee monotonic non-decreasing
        next_offer = max(next_offer, current_offer_inr)

        is_terminal = (next_round == 3 or next_offer >= settlement_band.walkaway_cap_inr)
        if is_terminal and next_round < 3:
            round_state = NegotiationRoundState.ROUND_2_COUNTER

        reason = (
            f"Round {next_round} concession applied with alpha={alpha:.2f}. "
            f"Increased from ₹{current_offer_inr:,.2f} to ₹{next_offer:,.2f} (cap: ₹{round_cap:,.2f})."
        )
        return (next_round, next_offer, round_state, is_terminal, reason)


fsm_controller = NegotiationFSMController()

