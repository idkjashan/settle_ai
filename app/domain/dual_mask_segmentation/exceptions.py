from typing import Any, Dict, List, Optional
from app.core.exceptions import AutoSettleException


class Stage2ModelCompatibilityError(AutoSettleException):
    """Raised when a model checkpoint is missing, corrupted, or has an incompatible taxonomy.
    
    This is a critical pipeline configuration/compatibility failure, NOT a claim escalation.
    """
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="STAGE_2_MODEL_COMPATIBILITY_ERROR", details=details or {})


class Stage2Error(Exception):
    """Base exception for Stage 2 guardrails and escalations."""
    def __init__(self, message: str, failure_codes: List[str], escalation_code: str):
        super().__init__(message)
        self.message = message
        self.failure_codes = failure_codes
        self.escalation_code = escalation_code


class Stage2UnrepairedRepeatError(Stage2Error):
    """Raised when part already received cash-in-lieu without repair verification (ESC-03)."""
    def __init__(self, message: str, failure_codes: List[str]):
        super().__init__(message, failure_codes, escalation_code="ESC-03")


class Stage2OppositeSideMultiHitError(Stage2Error):
    """Raised when both left-side and right-side parts are claimed simultaneously (ESC-05)."""
    def __init__(self, message: str, failure_codes: List[str]):
        super().__init__(message, failure_codes, escalation_code="ESC-05")


class Stage2SafetyCriticalError(Stage2Error):
    """Raised when safety-critical parts or shattered glass/flat tires are detected (ESC-06)."""
    def __init__(self, message: str, failure_codes: List[str]):
        super().__init__(message, failure_codes, escalation_code="ESC-06")


class Stage2LowConfidenceOrNoDamageError(Stage2Error):
    """Raised when zero damage overlaps survive filtering or confidence < 0.45 (ESC-07)."""
    def __init__(self, message: str, failure_codes: List[str]):
        super().__init__(message, failure_codes, escalation_code="ESC-07")
