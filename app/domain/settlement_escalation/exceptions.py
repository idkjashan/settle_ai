"""
app/domain/settlement_escalation/exceptions.py
Exception hierarchy for Stage 6 Settlement Router & Escalation Dossier.
"""
from typing import Optional, Dict, Any
from app.core.exceptions import AutoSettleException


class SettlementError(AutoSettleException):
    """Base exception for Stage 6 settlement failures."""
    def __init__(self, message: str, code: str = "SETTLEMENT_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=code, details=details)


class VoucherGenerationError(SettlementError):
    """Raised when settlement voucher construction fails."""
    def __init__(self, message: str = "Failed to generate settlement voucher.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="VOUCHER_GENERATION_FAILED", details=details)


class EscalationDossierError(SettlementError):
    """Raised when building surveyor escalation review dossier fails."""
    def __init__(self, message: str = "Failed to construct escalation review dossier.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="ESCALATION_DOSSIER_FAILED", details=details)


class UnrepairedLedgerCommitError(SettlementError):
    """Raised when committing settled parts to unrepaired_claims_ledger fails."""
    def __init__(self, message: str = "Failed to commit records to unrepaired claims ledger.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="LEDGER_COMMIT_FAILED", details=details)


class PDFGenerationError(SettlementError):
    """Raised when ReportLab PDF rendering encounters an unrecoverable failure."""
    def __init__(self, message: str = "Failed to render PDF document.", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="PDF_GENERATION_FAILED", details=details)

