"""
app/domain/actuarial_pricing/ncb_advisor.py
No Claim Bonus (NCB) Economic Utility Evaluator.
"""
from decimal import Decimal

from app.domain.actuarial_pricing.enums import NCBRecommendation
from app.domain.actuarial_pricing.rules import quantize_inr
from app.domain.actuarial_pricing.schemas import NCBAdvisoryDTO


class NCBAdvisor:
    """
    Evaluates whether filing a motor own-damage claim is economically rational
    for the insured by comparing net payable claim liability against the estimated
    accumulated No Claim Bonus (NCB) discount lost at policy renewal.
    """

    @staticmethod
    def evaluate(
        net_claim_liability_inr: Decimal,
        estimated_ncb_loss_inr: Decimal,
    ) -> NCBAdvisoryDTO:
        """
        Evaluate claim economic utility against estimated renewal NCB loss.

        Args:
            net_claim_liability_inr: Calculated net insurer claim liability (C_net).
            estimated_ncb_loss_inr: Underwritten estimated renewal premium discount loss (L_ncb).

        Returns:
            NCBAdvisoryDTO with recommendation, quantified benefit/loss, and transparent message.
        """
        net_benefit = quantize_inr(net_claim_liability_inr - estimated_ncb_loss_inr)

        if net_claim_liability_inr <= Decimal("0.00") or net_benefit <= Decimal("0.00"):
            recommendation = NCBRecommendation.PAY_OUT_OF_POCKET
            penalty = quantize_inr(abs(net_benefit))
            message = (
                f"We recommend paying for this repair out-of-pocket. The net claim payout "
                f"of ₹{net_claim_liability_inr} is less than your estimated renewal No Claim "
                f"Bonus (NCB) discount loss of ₹{estimated_ncb_loss_inr}, resulting in a net "
                f"personal financial penalty of ₹{penalty} at renewal."
            )
        else:
            recommendation = NCBRecommendation.PROCEED_WITH_CLAIM
            message = (
                f"Filing this claim provides positive economic utility. Your net claim payout "
                f"of ₹{net_claim_liability_inr} exceeds your estimated renewal NCB loss of "
                f"₹{estimated_ncb_loss_inr} by ₹{net_benefit}."
            )

        return NCBAdvisoryDTO(
            recommendation=recommendation,
            net_claim_liability_inr=net_claim_liability_inr,
            estimated_ncb_loss_inr=estimated_ncb_loss_inr,
            net_benefit_inr=net_benefit,
            advisory_message=message,
        )
