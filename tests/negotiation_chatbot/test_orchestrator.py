"""
tests/negotiation_chatbot/test_orchestrator.py
Unit and async lifecycle tests for Stage 5 Negotiation Chatbot Orchestrator.
"""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
import uuid
import pytest
from app.domain.actuarial_pricing.enums import MaterialType, RepairAction, NCBRecommendation
from app.domain.actuarial_pricing.schemas import (
    ActuarialEstimateDTO,
    ActuarialLineItemDTO,
    ActuarialSummaryDTO,
    CashSettlementBandDTO,
    NCBAdvisoryDTO,
)
from app.domain.negotiation_chatbot.exceptions import (
    NegotiationError,
    NegotiationSessionTerminatedError,
)
from app.domain.negotiation_chatbot.orchestrator import Stage5NegotiationOrchestrator
from app.domain.negotiation_chatbot.schemas import (
    ClaimantMessageDTO,
    NegotiationRoundState,
)


@pytest.fixture
def mock_estimate() -> ActuarialEstimateDTO:
    claim_id = uuid.uuid4()
    line_item = ActuarialLineItemDTO(
        canonical_part_key="front_bumper",
        display_part_name="Front Bumper Cover",
        oem_part_number="86511-M0000",
        material=MaterialType.PLASTIC,
        action=RepairAction.REPLACE,
        depth_grade="L4_CREASED_DENT",
        iop_ratio=0.12,
        base_part_cost_inr=Decimal("8800.00"),
        depreciation_rate_pct=Decimal("0.00"),
        depreciation_amount_inr=Decimal("0.00"),
        net_part_cost_inr=Decimal("8800.00"),
        salvage_deduction_inr=Decimal("200.00"),
        rr_labour_inr=Decimal("850.00"),
        denting_labour_inr=Decimal("1100.00"),
        pdr_polish_flat_inr=Decimal("0.00"),
        base_paint_inr=Decimal("3800.00"),
        paint_multiplier=Decimal("1.00"),
        paint_overlap_discount=Decimal("0.00"),
        final_paint_inr=Decimal("3800.00"),
        pre_tax_total_inr=Decimal("14550.00"),
        gst_amount_inr=Decimal("2619.00"),
        gross_line_item_total_inr=Decimal("17169.00"),
    )
    summary = ActuarialSummaryDTO(
        total_gross_parts_inr=Decimal("8800.00"),
        total_depreciation_inr=Decimal("0.00"),
        total_net_parts_inr=Decimal("8800.00"),
        total_labour_inr=Decimal("1950.00"),
        total_paint_inr=Decimal("3800.00"),
        pre_tax_subtotal_inr=Decimal("14550.00"),
        total_gst_inr=Decimal("2619.00"),
        gross_garage_repair_inr=Decimal("17169.00"),
        total_salvage_deduction_inr=Decimal("200.00"),
        compulsory_deductible_inr=Decimal("1000.00"),
        voluntary_deductible_inr=Decimal("0.00"),
        total_deductible_inr=Decimal("1000.00"),
        net_claim_liability_inr=Decimal("15969.00"),
    )
    band = CashSettlementBandDTO(
        initial_offer_inr=Decimal("11976.75"),
        target_settlement_inr=Decimal("13573.65"),
        walkaway_cap_inr=Decimal("15170.55"),
        financial_ceiling_inr=Decimal("25000.00"),
    )
    ncb = NCBAdvisoryDTO(
        recommendation=NCBRecommendation.PROCEED_WITH_CLAIM,
        net_claim_liability_inr=Decimal("15969.00"),
        estimated_ncb_loss_inr=Decimal("3200.00"),
        net_benefit_inr=Decimal("12769.00"),
        advisory_message="Claiming is financially advantageous.",
    )
    return ActuarialEstimateDTO(
        claim_id=claim_id,
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        vehicle_make="Hyundai",
        vehicle_model="Creta",
        vehicle_year=2023,
        calculation_timestamp=datetime.now(timezone.utc),
        is_zero_dep_active=True,
        line_items=[line_item],
        summary=summary,
        settlement_band=band,
        ncb_advisory=ncb,
    )


@pytest.fixture
def mock_redis():
    mgr = AsyncMock()
    client = AsyncMock()
    mgr.get_client = AsyncMock(return_value=client)
    mgr.publish_event = AsyncMock()
    return mgr


@pytest.fixture
def orchestrator(mock_redis):
    return Stage5NegotiationOrchestrator(
        db_session=None,
        redis_mgr=mock_redis,
    )


@pytest.mark.asyncio
async def test_session_initialization_from_estimate(orchestrator, mock_estimate, mock_redis):
    """Tests session initialization from ActuarialEstimateDTO, initial card signing, and SSE publishing."""
    session = await orchestrator.initialize_session(mock_estimate)

    assert session.claim_id == mock_estimate.claim_id
    assert session.current_round == 0
    assert session.session_state == NegotiationRoundState.ROUND_0_INITIAL
    assert session.active_offer_card.amount_inr == mock_estimate.settlement_band.initial_offer_inr
    assert len(session.turns) == 1
    assert session.turns[0].round_num == 0

    # Verify Redis cache storage and SSE event
    client = await mock_redis.get_client()
    assert client.set.called
    mock_redis.publish_event.assert_called_once()
    assert mock_redis.publish_event.call_args[1]["event_name"] == "CLAIM_OFFER_READY"


@pytest.mark.asyncio
async def test_process_claimant_turn(orchestrator, mock_estimate, mock_redis):
    """Tests processing a negotiation turn, recalculating offer, and updating session state."""
    session = await orchestrator.initialize_session(mock_estimate)

    client = await mock_redis.get_client()
    client.get = AsyncMock(return_value=session.model_dump_json())

    message_dto = ClaimantMessageDTO(
        message="The painting cost is higher, I need ₹14,000",
        counteroffer_inr=Decimal("14000.00"),
    )
    turn = await orchestrator.process_claimant_turn(mock_estimate.claim_id, message_dto)

    assert turn.round_num == 1
    assert turn.offered_amount_inr > mock_estimate.settlement_band.initial_offer_inr
    assert turn.offered_amount_inr <= mock_estimate.settlement_band.target_settlement_inr
    assert turn.offer_card.is_terminal is False

    assert mock_redis.publish_event.call_count >= 2
    last_event = mock_redis.publish_event.call_args_list[-1][1]
    assert last_event["event_name"] == "NEGOTIATION_TURN_COMPLETED"
    assert last_event["payload"]["round_num"] == 1


@pytest.mark.asyncio
async def test_session_termination_error(orchestrator, mock_estimate, mock_redis):
    """Verifies that operating on an already settled or rejected session raises NegotiationSessionTerminatedError."""
    session = await orchestrator.initialize_session(mock_estimate)

    settled_session = session.model_copy(update={"session_state": NegotiationRoundState.SETTLED})
    client = await mock_redis.get_client()
    client.get = AsyncMock(return_value=settled_session.model_dump_json())

    with pytest.raises(NegotiationSessionTerminatedError):
        await orchestrator.process_claimant_turn(
            mock_estimate.claim_id,
            ClaimantMessageDTO(message="Can you give more?"),
        )


@pytest.mark.asyncio
async def test_missing_session_error(orchestrator, mock_redis):
    """Verifies that processing a turn for a non-existent claim raises NegotiationError."""
    client = await mock_redis.get_client()
    client.get = AsyncMock(return_value=None)

    with pytest.raises(NegotiationError) as exc_info:
        await orchestrator.process_claimant_turn(
            uuid.uuid4(),
            ClaimantMessageDTO(message="Hello"),
        )
    assert "No active negotiation session found" in str(exc_info.value)