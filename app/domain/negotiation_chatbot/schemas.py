"""
app/domain/negotiation_chatbot/schemas.py
Pydantic v2 DTOs and Enums for Stage 5 Negotiation Chatbot FSM.
"""
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict
from app.domain.actuarial_pricing.schemas import CashSettlementBandDTO


class NegotiationRoundState(str, Enum):
    ROUND_0_INITIAL = "ROUND_0_INITIAL"
    ROUND_1_COUNTER = "ROUND_1_COUNTER"
    ROUND_2_COUNTER = "ROUND_2_COUNTER"
    ROUND_3_FINAL = "ROUND_3_FINAL"
    SETTLED = "SETTLED"
    REJECTED_GARAGE = "REJECTED_GARAGE"


class ClaimantIntent(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT_GARAGE = "REJECT_GARAGE"
    COUNTER = "COUNTER"
    QUALITATIVE_PLEA = "QUALITATIVE_PLEA"


class OfferCardDTO(BaseModel):
    """Cryptographically signed offer card displayed in claimant UI."""
    model_config = ConfigDict(frozen=True)

    claim_id: UUID
    round_num: int
    amount_inr: Decimal
    formatted_amount: str
    expires_at_epoch: int
    hmac_signature: str
    is_terminal: bool = False
    breakdown_summary: str = ""

    def to_dict(self, mode: str = "json") -> Dict[str, Any]:
        return self.model_dump(mode=mode)


class ClaimantMessageDTO(BaseModel):
    """Incoming user chat message or counteroffer payload."""
    model_config = ConfigDict(frozen=True)

    message: str
    counteroffer_inr: Optional[Decimal] = None

    def to_dict(self, mode: str = "json") -> Dict[str, Any]:
        return self.model_dump(mode=mode)


class NegotiationTurnDTO(BaseModel):
    """Record of a single conversational negotiation exchange."""
    model_config = ConfigDict(frozen=True)

    round_num: int
    claimant_message: str
    parsed_counteroffer_inr: Optional[Decimal]
    rationale_score: float
    offered_amount_inr: Decimal
    chatbot_reply: str
    offer_card: OfferCardDTO
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self, mode: str = "json") -> Dict[str, Any]:
        return self.model_dump(mode=mode)


class NegotiationSessionDTO(BaseModel):
    """Master state container for an active claim negotiation session."""
    model_config = ConfigDict(frozen=True)

    claim_id: UUID
    policy_id: str
    registration_number: str
    current_round: int
    session_state: NegotiationRoundState
    settlement_band: CashSettlementBandDTO
    active_offer_card: OfferCardDTO
    turns: List[NegotiationTurnDTO] = Field(default_factory=list)

    def to_dict(self, mode: str = "json") -> Dict[str, Any]:
        return self.model_dump(mode=mode)

