"""
app/domain/negotiation_chatbot/presenter.py
Conversational presentation layer formatting mathematical FSM outcomes into empathetic claimant dialogue.
Includes 100% deterministic template fallback for hermetic/offline execution.
"""
from decimal import Decimal
from typing import Optional
from app.domain.actuarial_pricing.schemas import ActuarialEstimateDTO
from app.domain.negotiation_chatbot.schemas import (
    ClaimantIntent,
    NegotiationRoundState,
)


class NegotiationPresenter:
    """
    Formats FSM calculation outcomes into human-readable, transparent claims explanations.
    """

    def present_initial_offer(
        self,
        estimate: ActuarialEstimateDTO,
        initial_offer_inr: Decimal,
    ) -> str:
        """Presents the initial cash-in-lieu settlement offer (Round 0)."""
        line_item_count = len(estimate.line_items)
        ncb_msg = estimate.ncb_advisory.advisory_message

        parts_summary = ", ".join(f"{item.display_part_name} ({item.action.value.lower()})" for item in estimate.line_items[:3])
        if line_item_count > 3:
            parts_summary += f" and {line_item_count - 3} other components"

        return (
            f"Hello! We've completed the forensic video inspection of your {estimate.vehicle_make} {estimate.vehicle_model} "
            f"({estimate.registration_number}). Our actuarial assessment covers {parts_summary}.\n\n"
            f"• Gross Garage Estimate: ₹{estimate.summary.gross_garage_repair_inr:,.2f}\n"
            f"• Statutory Deductible / Salvage: -₹{estimate.summary.total_deductible_inr + estimate.summary.total_salvage_deduction_inr:,.2f}\n"
            f"• Net Insurer Liability: ₹{estimate.summary.net_claim_liability_inr:,.2f}\n\n"
            f"We are pleased to present an instant Cash-in-Lieu settlement offer of ₹{initial_offer_inr:,.2f} directly to your bank account via UPI/IMPS. "
            f"{ncb_msg}\n\n"
            f"You can accept this instant payout now, or reply with any questions or quotes if you'd like us to review."
        )

    def present_counteroffer_response(
        self,
        round_num: int,
        offered_amount_inr: Decimal,
        is_terminal: bool,
        intent: ClaimantIntent,
        transition_reason: str,
        user_message: str,
    ) -> str:
        """Presents the response to a claimant's counteroffer or feedback."""
        if intent == ClaimantIntent.ACCEPT:
            return (
                f"Thank you! You have accepted our cash settlement offer of ₹{offered_amount_inr:,.2f}. "
                f"Your digital settlement voucher has been generated, and your instant payout is being dispatched."
            )

        if intent == ClaimantIntent.REJECT_GARAGE:
            return (
                f"Understood. We have transferred your claim to our Authorized Network Cashless Garage queue. "
                f"A surveyor work order has been generated, and our nearest partner workshop will contact you for vehicle drop-off."
            )

        if is_terminal or round_num >= 3:
            return (
                f"We have thoroughly reviewed your request regarding your vehicle repair. "
                f"We have adjusted our offer to our maximum authorized cash settlement cap of ₹{offered_amount_inr:,.2f}.\n\n"
                f"This represents our final walk-away settlement. You may accept this instant cash payout of ₹{offered_amount_inr:,.2f}, "
                f"or if you prefer full physical workshop restoration, you can choose cashless repair at an authorized network garage."
            )

        if "lower than current offer" in transition_reason:
            return (
                f"Thank you for your message. We noticed your figure was lower than our existing offer. "
                f"To ensure you receive the fairest payout, we are keeping our higher approved offer of ₹{offered_amount_inr:,.2f} active for you."
            )

        # Standard round progression
        return (
            f"Thank you for sharing your feedback. Based on your comments regarding repair costs, "
            f"we have recalculated our cash allowance and increased our offer to ₹{offered_amount_inr:,.2f}.\n\n"
            f"This cash payout can be credited directly to your account immediately. Would you like to accept this offer?"
        )


negotiation_presenter = NegotiationPresenter()

