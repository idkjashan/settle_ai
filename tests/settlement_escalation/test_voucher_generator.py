"""
tests/settlement_escalation/test_voucher_generator.py
Unit tests for Settlement Voucher construction, Indian currency words, and SHA-256 seal calculation.
"""
from decimal import Decimal
import re
import uuid
import pytest
from app.domain.settlement_escalation.voucher_generator import (
    SettlementVoucherGenerator,
    number_to_indian_rupee_words,
)


@pytest.fixture
def generator() -> SettlementVoucherGenerator:
    return SettlementVoucherGenerator()


def test_canonical_voucher_id_format(generator):
    """Verifies canonical voucher ID format: VOUCHER-AUTOSETTLE-YYYYMMDD-XXXX."""
    voucher = generator.generate_voucher(
        claim_id=uuid.uuid4(),
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        vehicle_make_model="Hyundai Creta",
        settled_amount_inr=Decimal("12500.00"),
        apportioned_parts=[],
    )
    pattern = r"^VOUCHER-AUTOSETTLE-\d{8}-\d{4}$"
    assert re.match(pattern, voucher.voucher_id)


def test_disbursement_ref_format(generator):
    """Verifies canonical disbursement reference format: DISB-IMPS-YYYYMMDD-XXXXXX."""
    voucher = generator.generate_voucher(
        claim_id=uuid.uuid4(),
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        vehicle_make_model="Hyundai Creta",
        settled_amount_inr=Decimal("12500.00"),
        apportioned_parts=[],
    )
    pattern = r"^DISB-IMPS-\d{8}-\d{6}$"
    assert re.match(pattern, voucher.disbursement_ref)


@pytest.mark.parametrize(
    "amount,expected_words",
    [
        (Decimal("12500.00"), "Twelve Thousand Five Hundred Rupees Only"),
        (Decimal("0.00"), "Zero Rupees Only"),
        (Decimal("100000.00"), "One Lakh Rupees Only"),
        (Decimal("25000.50"), "Twenty Five Thousand Rupees and Fifty Paise Only"),
        (Decimal("1500000.00"), "Fifteen Lakh Rupees Only"),
        (Decimal("10000000.00"), "One Crore Rupees Only"),
    ],
)
def test_number_to_indian_rupee_words(amount, expected_words):
    """Tests conversion of currency amounts to Indian English words."""
    result = number_to_indian_rupee_words(amount)
    assert result == expected_words


def test_sha256_digital_certificate_seal(generator):
    """Verifies that the digital_signature_sha256 is a valid 64-character SHA-256 hex digest."""
    claim_id = uuid.uuid4()
    voucher = generator.generate_voucher(
        claim_id=claim_id,
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        vehicle_make_model="Hyundai Creta",
        settled_amount_inr=Decimal("12500.00"),
        apportioned_parts=[],
        beneficiary_upi_id="claimant@okhdfcbank",
    )

    assert isinstance(voucher.digital_signature_sha256, str)
    assert len(voucher.digital_signature_sha256) == 64
    assert voucher.beneficiary_upi_id == "claimant@okhdfcbank"