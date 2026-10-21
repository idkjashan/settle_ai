"""
tests/settlement_escalation/test_orchestrator.py
Unit and async integration tests for Stage 6 Settlement Orchestrator.
"""
from decimal import Decimal
from unittest.mock import AsyncMock
import uuid
import pytest
from app.domain.negotiation_chatbot.exceptions import InvalidOfferTokenError
from app.domain.negotiation_chatbot.hmac_signer import hmac_offer_signer
from app.domain.negotiation_chatbot.schemas import OfferCardDTO
from app.domain.settlement_escalation.orchestrator import Stage6SettlementOrchestrator
from app.domain.settlement_escalation.schemas import SettlementVoucherDTO
from tests.in_memory_db import FakeAsyncSession, in_memory_db, patch_in_memory_db
from app.infrastructure.db.models import Claim

patch_in_memory_db()


@pytest.fixture
def mock_claim():
    claim_id = uuid.uuid4()
    claim = Claim(
        claim_id=claim_id,
        policy_id="POL-HAPPY-001",
        video_sha256="fake_sha256",
        current_stage="STAGE_5_NEGOTIATION",
        claim_status="NEGOTIATION_IN_PROGRESS",
        actuarial_estimate={
            "line_items": [
                {
                    "canonical_part_key": "front_bumper",
                    "display_part_name": "Front Bumper Cover",
                    "oem_part_number": "86511-M0000",
                    "material": "plastic",
                    "action": "REPLACE",
                    "depth_grade": "L4_CREASED_DENT",
                    "iop_ratio": 0.15,
                    "base_part_cost_inr": "8800.00",
                    "depreciation_rate_pct": "0.00",
                    "depreciation_amount_inr": "0.00",
                    "net_part_cost_inr": "8800.00",
                    "salvage_deduction_inr": "200.00",
                    "rr_labour_inr": "850.00",
                    "denting_labour_inr": "1100.00",
                    "pdr_polish_flat_inr": "0.00",
                    "base_paint_inr": "3800.00",
                    "paint_multiplier": "1.00",
                    "paint_overlap_discount": "0.00",
                    "final_paint_inr": "3800.00",
                    "pre_tax_total_inr": "14550.00",
                    "gst_amount_inr": "2619.00",
                    "gross_line_item_total_inr": "17169.00",
                }
            ],
            "summary": {"net_claim_liability_inr": "15969.00"},
        },
    )
    in_memory_db.claims[claim_id] = claim
    return claim


@pytest.fixture
def orchestrator():
    db = FakeAsyncSession()
    mock_redis = AsyncMock()
    mock_redis.publish_event = AsyncMock()
    return Stage6SettlementOrchestrator(
        db_session=db,
        redis_mgr=mock_redis,
    )


@pytest.mark.asyncio
async def test_finalize_settlement_happy_path(orchestrator, mock_claim):
    """
    Tests successful settlement finalization:
    - Validates HMAC offer card signature
    - Executes pro-rata apportionment
    - Commits damaged part to unrepaired ledger
    - Issues SettlementVoucherDTO
    - Updates claim status to SETTLED_CASH_IN_LIEU
    - Emits CLAIM_SETTLED_CASH_IN_LIEU SSE event
    """
    amount = Decimal("11976.75")
    expires_at = hmac_offer_signer.generate_expiration_epoch()
    sig = hmac_offer_signer.sign_offer(mock_claim.claim_id, round_num=1, amount_inr=amount, expires_at_epoch=expires_at)

    offer_card = OfferCardDTO(
        claim_id=mock_claim.claim_id,
        round_num=1,
        amount_inr=amount,
        formatted_amount=f"₹{amount:,.2f}",
        expires_at_epoch=expires_at,
        hmac_signature=sig,
        is_terminal=False,
    )

    voucher = await orchestrator.finalize_settlement(
        claim_id=mock_claim.claim_id,
        accepted_offer=offer_card,
        beneficiary_upi_id="claimant@okhdfcbank",
    )

    assert isinstance(voucher, SettlementVoucherDTO)
    assert voucher.settled_amount_inr == amount
    assert voucher.beneficiary_upi_id == "claimant@okhdfcbank"
    assert len(voucher.apportioned_parts) == 1
    assert mock_claim.claim_status == "SETTLED_CASH_IN_LIEU"

    orchestrator.redis_mgr.publish_event.assert_called_once()
    call_args = orchestrator.redis_mgr.publish_event.call_args[1]
    assert call_args["event_name"] == "CLAIM_SETTLED_CASH_IN_LIEU"


@pytest.mark.asyncio
async def test_finalize_settlement_tamper_rejection(orchestrator, mock_claim):
    """Verifies that an offer card with a tampered amount is rejected with InvalidOfferTokenError."""
    amount = Decimal("11976.75")
    expires_at = hmac_offer_signer.generate_expiration_epoch()
    sig = hmac_offer_signer.sign_offer(mock_claim.claim_id, round_num=1, amount_inr=amount, expires_at_epoch=expires_at)

    tampered_offer = OfferCardDTO(
        claim_id=mock_claim.claim_id,
        round_num=1,
        amount_inr=Decimal("20000.00"),
        formatted_amount="₹20,000.00",
        expires_at_epoch=expires_at,
        hmac_signature=sig,
    )

    with pytest.raises(InvalidOfferTokenError):
        await orchestrator.finalize_settlement(mock_claim.claim_id, tampered_offer)


@pytest.mark.asyncio
async def test_escalate_claim_surveyor_review(orchestrator, mock_claim):
    """Verifies claim escalation to human reviewer (ESC-02) updates DB and publishes SSE."""
    dossier = await orchestrator.escalate_claim(
        claim_id=mock_claim.claim_id,
        escalation_code="ESC-02",
        escalation_reason="Video splicing detected.",
    )

    assert dossier.escalation_code == "ESC-02"
    assert mock_claim.claim_status == "ESCALATED_HUMAN_REVIEW"
    orchestrator.redis_mgr.publish_event.assert_called_once()
    assert orchestrator.redis_mgr.publish_event.call_args[1]["event_name"] == "CLAIM_ESCALATED"


@pytest.mark.asyncio
async def test_escalate_claim_cashless_garage(orchestrator, mock_claim):
    """Verifies claimant rejection routes to cashless garage (ESC-USER-REJECT)."""
    dossier = await orchestrator.escalate_claim(
        claim_id=mock_claim.claim_id,
        escalation_code="ESC-USER-REJECT",
    )

    assert dossier.escalation_code == "ESC-USER-REJECT"
    assert mock_claim.claim_status == "ROUTED_CASHLESS_GARAGE"
    orchestrator.redis_mgr.publish_event.assert_called_once()
    assert orchestrator.redis_mgr.publish_event.call_args[1]["event_name"] == "CLAIM_ROUTED_CASHLESS_GARAGE"