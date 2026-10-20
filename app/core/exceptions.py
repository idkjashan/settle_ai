from typing import Optional, List, Dict, Any

class AutoSettleException(Exception):
    """Base exception for Auto-Settle AI."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

class PayloadTooLargeException(AutoSettleException):
    def __init__(self, message: str = "Video file exceeds 100 MB maximum threshold."):
        super().__init__(message, code="PAYLOAD_TOO_LARGE")

class LockConflictException(AutoSettleException):
    def __init__(self, message: str = "A claim with this video hash is currently processing."):
        super().__init__(message, code="LOCK_CONFLICT")

class FastFailException(AutoSettleException):
    def __init__(self, failure_codes: List[str], user_message: str, telemetry: Optional[Dict[str, Any]] = None, can_retry: bool = True):
        super().__init__(user_message, code="ESC-00", details={"failure_codes": failure_codes, "telemetry": telemetry, "can_retry": can_retry})
        self.failure_codes = failure_codes
        self.user_message = user_message
        self.telemetry = telemetry or {}
        self.can_retry = can_retry

class Stage1IdentityException(AutoSettleException):
    def __init__(self, message: str, failure_code: str = "ESC-01", telemetry: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=failure_code, details={"telemetry": telemetry})
        self.telemetry = telemetry or {}

class Stage1ContinuityException(AutoSettleException):
    def __init__(self, message: str, failure_code: str = "ESC-02", telemetry: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=failure_code, details={"telemetry": telemetry})
        self.telemetry = telemetry or {}

