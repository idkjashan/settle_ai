"""
app/domain/negotiation_chatbot/exceptions.py
Exception hierarchy for Stage 5 Negotiation Chatbot FSM.
"""
from typing import Optional, Dict, Any
from app.core.exceptions import AutoSettleException


class NegotiationError(AutoSettleException):
    """Base exception for Stage 5 negotiation failures."""
    def __init__(self, message: str, code: str = "NEGOTIATION_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=code, details=details)


class InvalidOfferTokenError(NegotiationError):
    """Raised when an HMAC offer signature is invalid, forged, or expired."""
    def __init__(self, message: str = "Offer card signature is invalid or has expired.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="INVALID_OFFER_TOKEN", details=details)


class NegotiationRoundExhaustedError(NegotiationError):
    """Raised when attempting to submit a counteroffer after Round 3 has locked."""
    def __init__(self, message: str = "Negotiation rounds exhausted. Only final acceptance or garage repair permitted.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="ROUNDS_EXHAUSTED", details=details)


class NegotiationSessionTerminatedError(NegotiationError):
    """Raised when operating on an already settled or escalated negotiation session."""
    def __init__(self, message: str = "Negotiation session has already terminated.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="SESSION_TERMINATED", details=details)


class AnchorInversionWarning(NegotiationError):
    """Raised when claimant submits a counteroffer lower than or equal to current offer."""
    def __init__(self, message: str = "Counteroffer is lower than or equal to existing offer.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="ANCHOR_INVERSION", details=details)

