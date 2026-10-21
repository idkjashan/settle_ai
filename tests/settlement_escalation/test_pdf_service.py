"""
tests/settlement_escalation/test_pdf_service.py
ReportLab PDF generation tests for Settlement Vouchers and Human Adjuster Dossiers.
"""
from decimal import Decimal
import uuid
import pytest
from app.domain.settlement_escalation.pdf_service import ReportLabPDFService
from app.domain.settlement_escalation.schemas import (
    ApportionedPartPayoutDTO,
    HumanAdjusterDossierDTO,
    SettlementVoucherDTO,
)


@pytest.fixture
def pdf_service() -> ReportLabPDFService:
    return ReportLabPDFService()


def test_generate_settlement_voucher_pdf(pdf_service):
    """Verifies ReportLab PDF generation for Settlement Voucher: produces valid PDF bytes."""
    part = ApportionedPartPayoutDTO(
        canonical_part_key="front_bumper",
        display_part_name="Front Bumper Cover",
        damage_class="L4_CREASED_DENT",
        gross_line_item_inr=Decimal("10000.00"),
        apportioned_amount_inr=Decimal("8500.00"),
    )
    voucher = SettlementVoucherDTO(
        voucher_id="VOUCHER-AUTOSETTLE-20261021-1234",
        claim_id=uuid.uuid4(),
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        vehicle_make_model="Hyundai Creta",
        settled_amount_inr=Decimal("8500.00"),
        settled_amount_words="Eight Thousand Five Hundred Rupees Only",
        beneficiary_upi_id="insured@okhdfcbank",
        disbursement_ref="DISB-IMPS-20261021-998877",
        apportioned_parts=[part],
        digital_signature_sha256="a" * 64,
    )

    pdf_bytes = pdf_service.generate_settlement_voucher_pdf(voucher)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF")


def test_generate_adjuster_dossier_pdf(pdf_service):
    """Verifies ReportLab PDF generation for Adjuster Dossier: produces valid PDF bytes."""
    dossier = HumanAdjusterDossierDTO(
        dossier_id="DOSSIER-ESC-02-20261021-4321",
        claim_id=uuid.uuid4(),
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        escalation_code="ESC-02",
        escalation_reason="Video Continuity Splicing / Scene Cut Detected",
        recommended_surveyor_action="Require mandatory in-person garage physical surveyor assessment.",
        forensic_telemetry={"cut_detected": True},
        surveyor_checklist=["Check VIN stamp", "Check HSRP plate rivets"],
    )

    pdf_bytes = pdf_service.generate_adjuster_dossier_pdf(dossier)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF")