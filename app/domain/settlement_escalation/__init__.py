"""
app/domain/settlement_escalation/__init__.py
Public exports for Stage 6 Settlement Router & Escalation Dossier.
"""
from app.domain.settlement_escalation.exceptions import (
    SettlementError,
    VoucherGenerationError,
    EscalationDossierError,
    UnrepairedLedgerCommitError,
    PDFGenerationError,
)
from app.domain.settlement_escalation.schemas import (
    ApportionedPartPayoutDTO,
    SettlementVoucherDTO,
    HumanAdjusterDossierDTO,
)
from app.domain.settlement_escalation.apportionment import (
    MultiPartApportionmentEngine,
    apportionment_engine,
)
from app.domain.settlement_escalation.voucher_generator import (
    SettlementVoucherGenerator,
    voucher_generator,
    number_to_indian_rupee_words,
)
from app.domain.settlement_escalation.dossier_builder import (
    HumanAdjusterDossierBuilder,
    dossier_builder,
)
from app.domain.settlement_escalation.pdf_service import (
    ReportLabPDFService,
    reportlab_pdf_service,
)
from app.domain.settlement_escalation.orchestrator import (
    Stage6SettlementOrchestrator,
)

# Architectural alias matching project LLD specification
SettlementEscalationEngine = Stage6SettlementOrchestrator

__all__ = [
    "SettlementError",
    "VoucherGenerationError",
    "EscalationDossierError",
    "UnrepairedLedgerCommitError",
    "PDFGenerationError",
    "ApportionedPartPayoutDTO",
    "SettlementVoucherDTO",
    "HumanAdjusterDossierDTO",
    "MultiPartApportionmentEngine",
    "apportionment_engine",
    "SettlementVoucherGenerator",
    "voucher_generator",
    "number_to_indian_rupee_words",
    "HumanAdjusterDossierBuilder",
    "dossier_builder",
    "ReportLabPDFService",
    "reportlab_pdf_service",
    "Stage6SettlementOrchestrator",
    "SettlementEscalationEngine",
]

