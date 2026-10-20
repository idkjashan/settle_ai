from typing import Optional, Dict, Any, List
from app.core.exceptions import AutoSettleException


class Stage1Error(Exception):
    """Base domain exception for Stage 1 per LLD Section 10.2."""
    def __init__(self, message: str, failure_codes: List[str], escalation_code: str):
        super().__init__(message)
        self.message = message
        self.failure_codes = failure_codes
        self.escalation_code = escalation_code


class Stage1IdentityError(Stage1Error):
    """Raised when vehicle identity, plate, or color check fails (ESC-01)."""
    def __init__(self, message: str, failure_codes: List[str]):
        super().__init__(message, failure_codes, escalation_code="ESC-01")


class Stage1ContinuityError(Stage1Error):
    """Raised when video splice, cut, or track loss occurs (ESC-02)."""
    def __init__(self, message: str, failure_codes: List[str]):
        super().__init__(message, failure_codes, escalation_code="ESC-02")


class IdentityContinuityException(AutoSettleException):
    """Base exception for Stage 1 FastAPI mapping."""
    def __init__(self, message: str, escalation_code: str, failure_reason: str, telemetry: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=escalation_code, details={"failure_reason": failure_reason, "telemetry": telemetry})
        self.escalation_code = escalation_code
        self.failure_reason = failure_reason
        self.telemetry = telemetry or {}


class VehicleIdentityException(IdentityContinuityException):
    def __init__(self, message: str, failure_reason: str, telemetry: Optional[Dict[str, Any]] = None):
        super().__init__(message, escalation_code="ESC-01", failure_reason=failure_reason, telemetry=telemetry)


class VideoContinuityException(IdentityContinuityException):
    def __init__(self, message: str, failure_reason: str, telemetry: Optional[Dict[str, Any]] = None):
        super().__init__(message, escalation_code="ESC-02", failure_reason=failure_reason, telemetry=telemetry)
