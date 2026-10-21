"""
tests/api/test_stage5_stage6_endpoints.py
Integration tests for unified Stage 5 & Stage 6 FastAPI claims router endpoints.
"""
from decimal import Decimal
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.domain.negotiation_chatbot.hmac_signer import hmac_offer_signer
from app.domain.negotiation_chatbot.schemas import (
    ClaimantMessageDTO,
    NegotiationRoundState,
    NegotiationSessionDTO,
    NegotiationTurnDTO,
    OfferCardDTO,
)
from app.domain.settlement_escalation.schemas import SettlementVoucherDTO
from app.infrastructure.db.models import Claim
from app.main import app
from app.infrastructure.db.session import get_db_session
from tests.in_memory_db import in_memory_db, patch_in_memory_db, FakeAsyncSession

patch_in_memory_db()


async def override_get_db_session():
    yield FakeAsyncSession()


app.dependency_overrides[get_db_session] = override_get_db_session


@pytest.fixture
def sample_claim():
    claim_id = uuid.uuid4()
    amount = Decimal("8500.00")
    expires_at = hmac_offer_signer.generate_expiration_epoch()
    sig = hmac_offer_signer.sign_offer(claim_id, round_num=0, amount_inr=amount, expires_at_epoch=expires_at)

    card = OfferCardDTO(
        claim_id=claim_id,
        round_num=0,
        amount_inr=amount,
        formatted_amount=f"₹{amount:,.2f}",
        expires_at_epoch=expires_at,
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
        video_sha256="test_sha_stage5",
        current_stage="STAGE_5_NEGOTIATION",
        claim_status="PRICED_READY_FOR_NEGOTIATION",
        negotiation_session=session.to_dict(),
        actuarial_estimate={
            "line_items": [
                {
                    "canonical_part_key": "front_bumper",
                    "display_part_name": "Front Bumper",
                    "oem_part_number": "86511-M0000",
                    "material": "plastic",
                    "action": "REPLACE",
                    "depth_grade": "L3_SHALLOW_DENT_PDR",
                    "iop_ratio": 0.10,
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
    return claim, card


@pytest.mark.asyncio
async def test_negotiate_claim_endpoint(sample_claim):
    """Tests POST /api/v1/claims/{claim_id}/negotiate."""
    claim, _ = sample_claim
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"message": "Can you please increase the offer to ₹9500?", "counteroffer_inr": "9500.00"}
        resp = await client.post(f"/api/v1/claims/{claim.claim_id}/negotiate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["round_num"] == 1
        assert Decimal(data["offered_amount_inr"]) > Decimal("8500.00")
        assert "offer_card" in data


@pytest.mark.asyncio
async def test_accept_settlement_offer_endpoint(sample_claim):
    """Tests POST /api/v1/claims/{claim_id}/accept."""
    claim, card = sample_claim
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "offer_card": card.to_dict(),
            "beneficiary_upi_id": "testclaimant@upi",
        }
        resp = await client.post(f"/api/v1/claims/{claim.claim_id}/accept", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["voucher_id"].startswith("VOUCHER-AUTOSETTLE-")
        assert data["settled_amount_inr"] == "8500.00"
        assert data["beneficiary_upi_id"] == "testclaimant@upi"


@pytest.mark.asyncio
async def test_accept_offer_tamper_rejected(sample_claim):
    """Tests POST /api/v1/claims/{claim_id}/accept with tampered amount yields 403."""
    claim, card = sample_claim
    tampered_card = card.model_copy(update={"amount_inr": Decimal("25000.00")})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"offer_card": tampered_card.to_dict()}
        resp = await client.post(f"/api/v1/claims/{claim.claim_id}/accept", json=payload)
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_reject_cash_settlement_endpoint(sample_claim):
    """Tests POST /api/v1/claims/{claim_id}/reject."""
    claim, _ = sample_claim
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"reason": "Prefer authorized dealer workshop repair."}
        resp = await client.post(f"/api/v1/claims/{claim.claim_id}/reject", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ROUTED_CASHLESS_GARAGE"
        assert "dossier_id" in data


@pytest.mark.asyncio
async def test_get_negotiation_session_endpoint(sample_claim):
    """Tests GET /api/v1/claims/{claim_id}/negotiation."""
    claim, _ = sample_claim
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/claims/{claim.claim_id}/negotiation")
        assert resp.status_code == 200
        data = resp.json()
        assert data["claim_id"] == str(claim.claim_id)
        assert data["current_round"] == 0


@pytest.mark.asyncio
async def test_get_voucher_and_voucher_pdf_endpoints(sample_claim):
    """Tests GET /api/v1/claims/{claim_id}/voucher and /voucher/pdf."""
    claim, card = sample_claim
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First accept offer to create voucher
        await client.post(f"/api/v1/claims/{claim.claim_id}/accept", json={"offer_card": card.to_dict()})

        # Test JSON voucher
        resp = await client.get(f"/api/v1/claims/{claim.claim_id}/voucher")
        assert resp.status_code == 200
        assert resp.json()["voucher_id"].startswith("VOUCHER-AUTOSETTLE-")

        # Test PDF download
        pdf_resp = await client.get(f"/api/v1/claims/{claim.claim_id}/voucher/pdf")
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers["content-type"] == "application/pdf"
        assert f"voucher_{claim.claim_id}.pdf" in pdf_resp.headers["content-disposition"]
        assert pdf_resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_get_dossier_and_dossier_pdf_endpoints(sample_claim):
    """Tests GET /api/v1/claims/{claim_id}/dossier and /dossier/pdf."""
    claim, _ = sample_claim
    claim.escalation_code = "ESC-02"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test JSON dossier
        resp = await client.get(f"/api/v1/claims/{claim.claim_id}/dossier")
        assert resp.status_code == 200
        assert resp.json()["escalation_code"] == "ESC-02"

        # Test PDF dossier
        pdf_resp = await client.get(f"/api/v1/claims/{claim.claim_id}/dossier/pdf")
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers["content-type"] == "application/pdf"
        assert f"dossier_{claim.claim_id}.pdf" in pdf_resp.headers["content-disposition"]
        assert pdf_resp.content.startswith(b"%PDF")