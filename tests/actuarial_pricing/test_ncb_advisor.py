"""
tests/actuarial_pricing/test_ncb_advisor.py
Unit tests for No Claim Bonus (NCB) Economic Utility Advisor.
"""
from decimal import Decimal
import pytest

from app.domain.actuarial_pricing.enums import NCBRecommendation
from app.domain.actuarial_pricing.ncb_advisor import NCBAdvisor
from app.domain.actuarial_pricing.schemas import NCBAdvisoryDTO


class TestNCBAdvisor:
    """Tests for NCB economic rationality evaluation and customer transparency messaging."""

    def test_recommends_pay_out_of_pocket_when_loss_exceeds_payout(self):
        """
        LLD Edge Case 10:
        Net claim payout is ₹1,979.50.
        Estimated renewal NCB discount loss is ₹5,400.00.
        Net economic deficit = ₹1,979.50 - ₹5,400.00 = -₹3,420.50.
        Recommendation must be PAY_OUT_OF_POCKET.
        """
        advisory = NCBAdvisor.evaluate(
            net_claim_liability_inr=Decimal("1979.50"),
            estimated_ncb_loss_inr=Decimal("5400.00"),
        )

        assert isinstance(advisory, NCBAdvisoryDTO)
        assert advisory.recommendation == NCBRecommendation.PAY_OUT_OF_POCKET
        assert advisory.net_claim_liability_inr == Decimal("1979.50")
        assert advisory.estimated_ncb_loss_inr == Decimal("5400.00")
        assert advisory.net_benefit_inr == Decimal("-3420.50")
        assert "paying for this repair out-of-pocket" in advisory.advisory_message
        assert "₹1979.50" in advisory.advisory_message
        assert "₹5400.00" in advisory.advisory_message
        assert "penalty of ₹3420.50" in advisory.advisory_message

    def test_recommends_proceed_with_claim_when_payout_exceeds_loss(self):
        """
        Net claim payout is ₹10,000.00.
        Estimated renewal NCB discount loss is ₹3,200.00.
        Net economic benefit = ₹10,000.00 - ₹3,200.00 = ₹6,800.00.
        Recommendation must be PROCEED_WITH_CLAIM.
        """
        advisory = NCBAdvisor.evaluate(
            net_claim_liability_inr=Decimal("10000.00"),
            estimated_ncb_loss_inr=Decimal("3200.00"),
        )

        assert advisory.recommendation == NCBRecommendation.PROCEED_WITH_CLAIM
        assert advisory.net_claim_liability_inr == Decimal("10000.00")
        assert advisory.estimated_ncb_loss_inr == Decimal("3200.00")
        assert advisory.net_benefit_inr == Decimal("6800.00")
        assert "positive economic utility" in advisory.advisory_message
        assert "₹10000.00" in advisory.advisory_message
        assert "₹3200.00" in advisory.advisory_message
        assert "₹6800.00" in advisory.advisory_message

    def test_recommends_pay_out_of_pocket_when_net_claim_is_zero(self):
        """
        When net claim payout is ₹0.00 (below deductible):
        Customer receives ₹0.00 but loses renewal discount of ₹3,200.00.
        Recommendation must be PAY_OUT_OF_POCKET.
        """
        advisory = NCBAdvisor.evaluate(
            net_claim_liability_inr=Decimal("0.00"),
            estimated_ncb_loss_inr=Decimal("3200.00"),
        )

        assert advisory.recommendation == NCBRecommendation.PAY_OUT_OF_POCKET
        assert advisory.net_benefit_inr == Decimal("-3200.00")
        assert "paying for this repair out-of-pocket" in advisory.advisory_message

    def test_recommends_pay_out_of_pocket_at_exact_breakeven(self):
        """
        When net claim payout exactly equals estimated NCB loss:
        Net benefit = ₹0.00.
        Because filing a claim carries administrative friction and risks subsequent loss of NCB,
        recommendation defaults to PAY_OUT_OF_POCKET.
        """
        advisory = NCBAdvisor.evaluate(
            net_claim_liability_inr=Decimal("3200.00"),
            estimated_ncb_loss_inr=Decimal("3200.00"),
        )

        assert advisory.recommendation == NCBRecommendation.PAY_OUT_OF_POCKET
        assert advisory.net_benefit_inr == Decimal("0.00")
        assert "penalty of ₹0.00" in advisory.advisory_message

    def test_paisa_quantization_precision(self):
        """Ensure calculations with float-derived fractions quantize to paisa precision."""
        advisory = NCBAdvisor.evaluate(
            net_claim_liability_inr=Decimal("1234.567"),
            estimated_ncb_loss_inr=Decimal("1000.123"),
        )
        assert advisory.net_claim_liability_inr == Decimal("1234.567")
        assert advisory.net_benefit_inr == Decimal("234.44")

    def test_dto_serialization(self):
        """Ensure NCBAdvisoryDTO serializes cleanly to dict for database and API transmission."""
        advisory = NCBAdvisor.evaluate(
            net_claim_liability_inr=Decimal("5000.00"),
            estimated_ncb_loss_inr=Decimal("2000.00"),
        )
        d = advisory.to_dict()
        assert d["recommendation"] == "PROCEED_WITH_CLAIM"
        assert d["net_claim_liability_inr"] == "5000.00" or d["net_claim_liability_inr"] == Decimal("5000.00")
        assert "positive economic utility" in d["advisory_message"]
