"""
tests/evals/test_frontend_e2e_client.py
Integration tests validating the Frontend E2E test client against FastAPI router endpoints.
"""
from decimal import Decimal
from pathlib import Path
import pytest
import uuid

from app.domain.negotiation_chatbot.hmac_signer import hmac_offer_signer
from app.domain.negotiation_chatbot.schemas import (
    NegotiationRoundState,
    NegotiationSessionDTO,
    NegotiationTurnDTO,
    OfferCardDTO,
)
from app.infrastructure.db.models import Claim
from evals.frontend_e2e_runner import FrontendE2ETestClient
from tests.in_memory_db import in_memory_db

TEST_VIDEOS_DIR = Path("test_assets/videos")
REAL_HILUX = TEST_VIDEOS_DIR / "difficult/toyota_hilux_white_ute.mp4"
CAR_001 = TEST_VIDEOS_DIR / "simple/car_001.mp4"


@pytest.fixture(autouse=True)
def clean_db():
    in_memory_db.reset()
    yield
    in_memory_db.reset()


class TestFrontendE2EClient:
    """Verifies that FrontendE2ETestClient interacts with the claims API like a browser."""

    @pytest.mark.asyncio
    async def test_frontend_fast_fail_rejection(self, tmp_path):
        """Videos not meeting container standards receive instant fast-fail remediation."""
        client = FrontendE2ETestClient(artifacts_dir=tmp_path)
        # car_001.mp4 has height 360 which is below the 480/720 threshold
        res = await client.execute_full_claim_flow(
            video_path=CAR_001,
            policy_id="POL-HAPPY-001",
            claim_description="Scratched bumper",
        )
        assert res["success"] is True
        assert res["terminal_step"] == "FAST_FAIL_REJECTED"
        assert res["verdict"] == "REJECTED_STAGE0"
        assert "remediation" in res

    @pytest.mark.asyncio
    async def test_frontend_negotiation_and_settlement_flow(self, tmp_path):
        """Simulates frontend negotiating and accepting signed cash settlement offer."""
        client = FrontendE2ETestClient(artifacts_dir=tmp_path)

        # Seed claim in ready-for-negotiation state to test frontend negotiation & acceptance
        claim_id = uuid.uuid4()
        amount = Decimal("8500.00")
        exp = hmac_offer_signer.generate_expiration_epoch()
        sig = hmac_offer_signer.sign_offer(claim_id, 0, amount, exp)
        card = OfferCardDTO(
            claim_id=claim_id,
            round_num=0,
            amount_inr=amount,
            formatted_amount="₹8,500.00",
            expires_at_epoch=exp,
            hmac_signature=sig,
        )
        turn = NegotiationTurnDTO(
            round_num=0,
            claimant_message="<INITIAL>",
            parsed_counteroffer_inr=None,
            rationale_score=1.0,
            offered_amount_inr=amount,
            chatbot_reply="Initial offer presentation.",
            offer_card=card,
        )
        session = NegotiationSessionDTO(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            registration_number="MH12DE1433",
            current_round=0,
            session_state=NegotiationRoundState.ROUND_0_INITIAL,
            settlement_band={
                "initial_offer_inr": "8500.00",
                "target_settlement_inr": "10000.00",
                "walkaway_cap_inr": "11500.00",
                "financial_ceiling_inr": "25000.00",
            },
            active_offer_card=card,
            turns=[turn],
        )
        claim = Claim(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            video_sha256="test_sha_e2e",
            current_stage="STAGE_5_NEGOTIATION",
            claim_status="PRICED_READY_FOR_NEGOTIATION",
            negotiation_session=session.to_dict(),
            actuarial_estimate={
                "line_items": [
                    {
                        "canonical_part_key": "front_bumper",
                        "display_part_name": "Front Bumper Cover",
                        "oem_part_number": "86511-M0000",
                        "material": "plastic",
                        "action": "REPAIR",
                        "depth_grade": "L2_BASECOAT_SCRATCH",
                        "iop_ratio": 0.08,
                        "base_part_cost_inr": "6000.00",
                        "depreciation_rate_pct": "0.00",
                        "depreciation_amount_inr": "0.00",
                        "net_part_cost_inr": "6000.00",
                        "salvage_deduction_inr": "0.00",
                        "rr_labour_inr": "500.00",
                        "denting_labour_inr": "0.00",
                        "pdr_polish_flat_inr": "0.00",
                        "base_paint_inr": "2000.00",
                        "paint_multiplier": "1.00",
                        "paint_overlap_discount": "0.00",
                        "final_paint_inr": "2000.00",
                        "pre_tax_total_inr": "8500.00",
                        "gst_amount_inr": "1530.00",
                        "gross_line_item_total_inr": "10030.00",
                    }
                ],
                "summary": {"net_claim_liability_inr": "10030.00"},
            },
        )
        in_memory_db.claims[claim_id] = claim

        # Test negotiate endpoint directly via client
        async with client._get_client() as http_client:
            neg_resp = await http_client.post(
                f"/api/v1/claims/{claim_id}/negotiate",
                json={"message": "Can you offer ₹9500?", "counteroffer_inr": "9500.00"},
            )
            assert neg_resp.status_code == 200
            turn_data = neg_resp.json()
            assert turn_data["round_num"] == 1
            new_card = turn_data["offer_card"]

            # Accept offer
            accept_resp = await http_client.post(
                f"/api/v1/claims/{claim_id}/accept",
                json={"offer_card": new_card, "beneficiary_upi_id": "claimant@upi"},
            )
            assert accept_resp.status_code == 200
            voucher_data = accept_resp.json()
            assert voucher_data["voucher_id"].startswith("VOUCHER-AUTOSETTLE-")

            # Download PDF voucher
            pdf_resp = await http_client.get(f"/api/v1/claims/{claim_id}/voucher/pdf")
            assert pdf_resp.status_code == 200
            assert pdf_resp.content.startswith(b"%PDF")
            pdf_file = tmp_path / f"voucher_{claim_id}.pdf"
            pdf_file.write_bytes(pdf_resp.content)
            assert pdf_file.exists()
            assert pdf_file.stat().st_size > 1000
