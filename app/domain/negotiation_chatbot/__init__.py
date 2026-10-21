"""
app/domain/negotiation_chatbot/__init__.py
Public exports for Stage 5 Negotiation Chatbot FSM.
"""
from app.domain.negotiation_chatbot.exceptions import (
    NegotiationError,
    InvalidOfferTokenError,
    NegotiationRoundExhaustedError,
    NegotiationSessionTerminatedError,
    AnchorInversionWarning,
)
from app.domain.negotiation_chatbot.schemas import (
    NegotiationRoundState,
    ClaimantIntent,
    OfferCardDTO,
    ClaimantMessageDTO,
    NegotiationTurnDTO,
    NegotiationSessionDTO,
)
from app.domain.negotiation_chatbot.hmac_signer import (
    HMACOfferSigner,
    hmac_offer_signer,
)
from app.domain.negotiation_chatbot.nlp_parser import (
    NLPNegotiationParser,
    nlp_negotiation_parser,
)
from app.domain.negotiation_chatbot.fsm_controller import (
    NegotiationFSMController,
    fsm_controller,
)
from app.domain.negotiation_chatbot.presenter import (
    NegotiationPresenter,
    negotiation_presenter,
)
from app.domain.negotiation_chatbot.orchestrator import (
    Stage5NegotiationOrchestrator,
)

# Architectural alias matching project LLD specification
NegotiationChatbotEngine = Stage5NegotiationOrchestrator

__all__ = [
    "NegotiationError",
    "InvalidOfferTokenError",
    "NegotiationRoundExhaustedError",
    "NegotiationSessionTerminatedError",
    "AnchorInversionWarning",
    "NegotiationRoundState",
    "ClaimantIntent",
    "OfferCardDTO",
    "ClaimantMessageDTO",
    "NegotiationTurnDTO",
    "NegotiationSessionDTO",
    "HMACOfferSigner",
    "hmac_offer_signer",
    "NLPNegotiationParser",
    "nlp_negotiation_parser",
    "NegotiationFSMController",
    "fsm_controller",
    "NegotiationPresenter",
    "negotiation_presenter",
    "Stage5NegotiationOrchestrator",
    "NegotiationChatbotEngine",
]

