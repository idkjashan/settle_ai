"""
tests/negotiation_chatbot/test_hmac_signer.py
Cryptographic tests for HMAC-SHA256 offer card signing and anti-tamper verification.
"""
from decimal import Decimal
import time
import uuid
import pytest
from app.domain.negotiation_chatbot.hmac_signer import HMACOfferSigner


@pytest.fixture
def signer() -> HMACOfferSigner:
    return HMACOfferSigner(secret_key="test-secret-key-settleai-2026")


def test_signature_generation_and_verification(signer):
    """Verifies that an offer signed by HMACOfferSigner validates successfully."""
    claim_id = uuid.uuid4()
    round_num = 1
    amount_inr = Decimal("8500.50")
    expires_at = int(time.time()) + 900

    signature = signer.sign_offer(claim_id, round_num, amount_inr, expires_at)
    assert isinstance(signature, str)
    assert len(signature) == 64  # SHA-256 produces 64-char hex digest

    is_valid = signer.verify_offer(claim_id, round_num, amount_inr, expires_at, signature)
    assert is_valid is True


def test_tampering_amount_fails(signer):
    """Verifies that tampering with the offer amount causes verification failure."""
    claim_id = uuid.uuid4()
    round_num = 1
    amount_inr = Decimal("7500.00")
    expires_at = int(time.time()) + 900

    signature = signer.sign_offer(claim_id, round_num, amount_inr, expires_at)

    # Attacker inflates amount in DOM
    tampered_amount = Decimal("8500.00")
    assert signer.verify_offer(claim_id, round_num, tampered_amount, expires_at, signature) is False


def test_tampering_claim_id_fails(signer):
    """Verifies that an offer token cannot be replayed for a different claim_id."""
    claim_id_1 = uuid.uuid4()
    claim_id_2 = uuid.uuid4()
    round_num = 0
    amount_inr = Decimal("7500.00")
    expires_at = int(time.time()) + 900

    signature = signer.sign_offer(claim_id_1, round_num, amount_inr, expires_at)
    assert signer.verify_offer(claim_id_2, round_num, amount_inr, expires_at, signature) is False


def test_tampering_round_fails(signer):
    """Verifies that tampering with the round number causes verification failure."""
    claim_id = uuid.uuid4()
    round_num = 1
    amount_inr = Decimal("8000.00")
    expires_at = int(time.time()) + 900

    signature = signer.sign_offer(claim_id, round_num, amount_inr, expires_at)
    assert signer.verify_offer(claim_id, 2, amount_inr, expires_at, signature) is False


def test_tampering_expiry_fails(signer):
    """Verifies that modifying the expiration epoch invalidates the signature."""
    claim_id = uuid.uuid4()
    round_num = 0
    amount_inr = Decimal("7500.00")
    expires_at = int(time.time()) + 900

    signature = signer.sign_offer(claim_id, round_num, amount_inr, expires_at)
    tampered_expiry = expires_at + 3600
    assert signer.verify_offer(claim_id, round_num, amount_inr, tampered_expiry, signature) is False


def test_ttl_expiration(signer):
    """Verifies that an expired timestamp returns False even if signature matches."""
    claim_id = uuid.uuid4()
    round_num = 0
    amount_inr = Decimal("7500.00")
    expired_epoch = int(time.time()) - 60  # Expired 60s ago

    signature = signer.sign_offer(claim_id, round_num, amount_inr, expired_epoch)
    assert signer.verify_offer(claim_id, round_num, amount_inr, expired_epoch, signature) is False


def test_generate_expiration_epoch(signer):
    """Verifies default and custom TTL epoch generation."""
    now = int(time.time())
    ttl_epoch = signer.generate_expiration_epoch(ttl_seconds=300)
    assert ttl_epoch >= now + 299
    assert ttl_epoch <= now + 302


def test_payload_string_format(signer):
    """Verifies canonical payload colon-delimited structure."""
    cid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    payload = signer.create_payload_string(cid, round_num=2, amount_inr=Decimal("12500.5"), expires_at_epoch=1800000000)
    assert payload == "12345678-1234-5678-1234-567812345678:2:12500.50:1800000000"