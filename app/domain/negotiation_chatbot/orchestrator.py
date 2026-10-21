"""
app/domain/negotiation_chatbot/orchestrator.py
Async Orchestrator managing negotiation lifecycle, state caching, DB persistence, and SSE event streaming.
"""
from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.actuarial_pricing.schemas import ActuarialEstimateDTO
from app.domain.negotiation_chatbot.exceptions import (
    NegotiationError,
    NegotiationRoundExhaustedError,
    NegotiationSessionTerminatedError,
)
from app.domain.negotiation_chatbot.fsm_controller import NegotiationFSMController, fsm_controller
from app.domain.negotiation_chatbot.hmac_signer import HMACOfferSigner, hmac_offer_signer
from app.domain.negotiation_chatbot.nlp_parser import NLPNegotiationParser, nlp_negotiation_parser
from app.domain.negotiation_chatbot.presenter import NegotiationPresenter, negotiation_presenter
from app.domain.negotiation_chatbot.schemas import (
    ClaimantIntent,
    ClaimantMessageDTO,
    NegotiationRoundState,
    NegotiationSessionDTO,
    NegotiationTurnDTO,
    OfferCardDTO,
)
from app.infrastructure.cache.redis_manager import RedisManager, redis_manager
from app.infrastructure.db.repositories import ClaimRepository

logger = logging.getLogger(__name__)


class Stage5NegotiationOrchestrator:
    """
    Coordinates Stage 5 Negotiation Chatbot session initialization, turn execution,
    HMAC validation, database synchronization, and Server-Sent Events.
    """

    def __init__(
        self,
        db_session: Optional[AsyncSession] = None,
        redis_mgr: Optional[RedisManager] = None,
        fsm: Optional[NegotiationFSMController] = None,
        signer: Optional[HMACOfferSigner] = None,
        nlp: Optional[NLPNegotiationParser] = None,
        presenter: Optional[NegotiationPresenter] = None,
    ):
        self.db_session = db_session
        self.redis_mgr = redis_mgr or redis_manager
        self.fsm = fsm or fsm_controller
        self.signer = signer or hmac_offer_signer
        self.nlp = nlp or nlp_negotiation_parser
        self.presenter = presenter or negotiation_presenter

    def _redis_key(self, claim_id: UUID) -> str:
        return f"claim:negotiation:{claim_id}"

    async def initialize_session(
        self,
        estimate: ActuarialEstimateDTO,
    ) -> NegotiationSessionDTO:
        """
        Initializes Round 0 negotiation session from Stage 4 ActuarialEstimateDTO.
        Signs initial HMAC offer card, persists to Redis & PostgreSQL, emits SSE event.
        """
        claim_id = estimate.claim_id
        band = estimate.settlement_band
        initial_amount = band.initial_offer_inr

        expires_at = self.signer.generate_expiration_epoch()
        sig = self.signer.sign_offer(claim_id, round_num=0, amount_inr=initial_amount, expires_at_epoch=expires_at)

        initial_card = OfferCardDTO(
            claim_id=claim_id,
            round_num=0,
            amount_inr=initial_amount,
            formatted_amount=f"₹{initial_amount:,.2f}",
            expires_at_epoch=expires_at,
            hmac_signature=sig,
            is_terminal=False,
            breakdown_summary=f"Initial cash-in-lieu allowance (75% of net insurer liability ₹{estimate.summary.net_claim_liability_inr:,.2f})",
        )

        initial_reply = self.presenter.present_initial_offer(estimate, initial_amount)

        initial_turn = NegotiationTurnDTO(
            round_num=0,
            claimant_message="<INITIAL_OFFER_PRESENTATION>",
            parsed_counteroffer_inr=None,
            rationale_score=1.0,
            offered_amount_inr=initial_amount,
            chatbot_reply=initial_reply,
            offer_card=initial_card,
        )

        session = NegotiationSessionDTO(
            claim_id=claim_id,
            policy_id=estimate.policy_id,
            registration_number=estimate.registration_number,
            current_round=0,
            session_state=NegotiationRoundState.ROUND_0_INITIAL,
            settlement_band=band,
            active_offer_card=initial_card,
            turns=[initial_turn],
        )

        # Cache in Redis
        try:
            client = await self.redis_mgr.get_client()
            await client.set(self._redis_key(claim_id), json.dumps(session.to_dict()), ex=86400)
        except Exception as e:
            logger.warning(f"Failed to cache negotiation session in Redis for {claim_id}: {e}")

        # Persist in DB
        if self.db_session:
            try:
                claim_repo = ClaimRepository(self.db_session)
                await claim_repo.update_claim_stage(
                    claim_id=claim_id,
                    stage="STAGE_5_NEGOTIATION",
                    status="PRICED_READY_FOR_NEGOTIATION",
                    telemetry_update=session.to_dict(),
                    telemetry_column="negotiation_session",
                )
            except Exception as e:
                logger.error(f"Failed to update claim DB for {claim_id}: {e}")

        # Emit SSE Event
        try:
            await self.redis_mgr.publish_event(
                claim_id=claim_id,
                event_name="CLAIM_OFFER_READY",
                payload={
                    "claim_id": str(claim_id),
                    "round_num": 0,
                    "initial_offer_inr": str(initial_amount),
                    "offer_card": initial_card.to_dict(),
                },
            )
        except Exception as e:
            logger.warning(f"Failed to publish CLAIM_OFFER_READY event for {claim_id}: {e}")

        logger.info(f"Initialized Stage 5 negotiation session for claim {claim_id} with initial offer ₹{initial_amount}")
        return session

    async def get_session(self, claim_id: UUID) -> Optional[NegotiationSessionDTO]:
        """Retrieves session from Redis cache, falling back to PostgreSQL."""
        try:
            client = await self.redis_mgr.get_client()
            raw = await client.get(self._redis_key(claim_id))
            if raw:
                return NegotiationSessionDTO.model_validate_json(raw)
        except Exception as e:
            logger.warning(f"Redis get failed for negotiation session {claim_id}: {e}")

        try:
            claim_repo = ClaimRepository(self.db_session)
            claim = await claim_repo.get_by_id(claim_id)
            if claim and claim.negotiation_session:
                return NegotiationSessionDTO.model_validate(claim.negotiation_session)
        except Exception as e:
            logger.warning(f"DB get failed for negotiation session {claim_id}: {e}")

        return None

    async def process_claimant_turn(
        self,
        claim_id: UUID,
        message_dto: ClaimantMessageDTO,
    ) -> NegotiationTurnDTO:
        """
        Processes claimant message, computes next FSM offer, generates signed HMAC card,
        persists state, and emits SSE event.
        """
        session = await self.get_session(claim_id)
        if not session:
            raise NegotiationError(f"No active negotiation session found for claim {claim_id}")

        if session.session_state in (NegotiationRoundState.SETTLED, NegotiationRoundState.REJECTED_GARAGE):
            raise NegotiationSessionTerminatedError(
                f"Negotiation session for claim {claim_id} has already terminated with status '{session.session_state}'."
            )

        current_round = session.current_round
        current_offer = session.active_offer_card.amount_inr

        # 1. NLP Parse claimant input
        intent, parsed_counter, rationale_score = self.nlp.parse(
            raw_message=message_dto.message,
            current_offer_inr=current_offer,
            explicit_counteroffer=message_dto.counteroffer_inr,
        )

        # 2. FSM compute next offer
        next_round, next_offer, next_state, is_terminal, reason = self.fsm.compute_next_offer(
            current_round=current_round,
            current_offer_inr=current_offer,
            settlement_band=session.settlement_band,
            intent=intent,
            claimant_counteroffer_inr=parsed_counter,
            rationale_score=rationale_score,
        )

        # 3. Sign new Offer Card
        expires_at = self.signer.generate_expiration_epoch()
        sig = self.signer.sign_offer(claim_id, round_num=next_round, amount_inr=next_offer, expires_at_epoch=expires_at)

        new_card = OfferCardDTO(
            claim_id=claim_id,
            round_num=next_round,
            amount_inr=next_offer,
            formatted_amount=f"₹{next_offer:,.2f}",
            expires_at_epoch=expires_at,
            hmac_signature=sig,
            is_terminal=is_terminal,
            breakdown_summary=reason,
        )

        # 4. Generate dialogue response
        chatbot_reply = self.presenter.present_counteroffer_response(
            round_num=next_round,
            offered_amount_inr=next_offer,
            is_terminal=is_terminal,
            intent=intent,
            transition_reason=reason,
            user_message=message_dto.message,
        )

        # 5. Build Turn Record
        turn = NegotiationTurnDTO(
            round_num=next_round,
            claimant_message=message_dto.message,
            parsed_counteroffer_inr=parsed_counter,
            rationale_score=rationale_score,
            offered_amount_inr=next_offer,
            chatbot_reply=chatbot_reply,
            offer_card=new_card,
        )

        # 6. Update Session
        updated_turns = list(session.turns) + [turn]
        updated_session = NegotiationSessionDTO(
            claim_id=claim_id,
            policy_id=session.policy_id,
            registration_number=session.registration_number,
            current_round=next_round,
            session_state=next_state,
            settlement_band=session.settlement_band,
            active_offer_card=new_card,
            turns=updated_turns,
        )

        # Persist in Redis
        try:
            client = await self.redis_mgr.get_client()
            await client.set(self._redis_key(claim_id), json.dumps(updated_session.to_dict()), ex=86400)
        except Exception as e:
            logger.warning(f"Failed to update Redis negotiation session for {claim_id}: {e}")

        # Persist in DB
        try:
            claim_repo = ClaimRepository(self.db_session)
            claim_status = "NEGOTIATION_IN_PROGRESS"
            if next_state == NegotiationRoundState.SETTLED:
                claim_status = "SETTLED_CASH_IN_LIEU"
            elif next_state == NegotiationRoundState.REJECTED_GARAGE:
                claim_status = "ROUTED_CASHLESS_GARAGE"

            await claim_repo.update_claim_stage(
                claim_id=claim_id,
                stage="STAGE_5_NEGOTIATION",
                status=claim_status,
                telemetry_update=updated_session.to_dict(),
                telemetry_column="negotiation_session",
            )
        except Exception as e:
            logger.error(f"Failed to update claim DB for {claim_id}: {e}")

        # Emit SSE Event
        try:
            await self.redis_mgr.publish_event(
                claim_id=claim_id,
                event_name="NEGOTIATION_TURN_COMPLETED",
                payload={
                    "claim_id": str(claim_id),
                    "round_num": next_round,
                    "offered_amount_inr": str(next_offer),
                    "is_terminal": is_terminal,
                    "offer_card": new_card.to_dict(),
                },
            )
        except Exception as e:
            logger.warning(f"Failed to publish NEGOTIATION_TURN_COMPLETED for {claim_id}: {e}")

        return turn

