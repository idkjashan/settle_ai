"""
app/domain/negotiation_chatbot/hmac_signer.py
Cryptographic HMAC-SHA256 offer card generator and anti-tamper verifier.
"""
from decimal import Decimal
import hashlib
import hmac
import time
from typing import Optional
from uuid import UUID
from app.core.config import settings

DEFAULT_SECRET = "auto-settle-ai-hmac-secret-key-2026"
DEFAULT_OFFER_TTL_SECONDS = 900  # 15 minutes


class HMACOfferSigner:
    """
    Signs and verifies Offer Cards with HMAC-SHA256.
    Protects against client-side DOM tampering, replay attacks, and token forgery.
    """

    def __init__(self, secret_key: Optional[str] = None):
        key = secret_key or getattr(settings, "HMAC_SECRET_KEY", None) or DEFAULT_SECRET
        self._secret_bytes = key.encode("utf-8")

    def create_payload_string(
        self,
        claim_id: UUID,
        round_num: int,
        amount_inr: Decimal,
        expires_at_epoch: int,
    ) -> str:
        """Constructs canonical colon-delimited payload string."""
        return f"{claim_id}:{round_num}:{amount_inr:.2f}:{expires_at_epoch}"

    def sign_offer(
        self,
        claim_id: UUID,
        round_num: int,
        amount_inr: Decimal,
        expires_at_epoch: int,
    ) -> str:
        """Generates HMAC-SHA256 hex digest for an offer."""
        payload = self.create_payload_string(claim_id, round_num, amount_inr, expires_at_epoch)
        return hmac.new(self._secret_bytes, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify_offer(
        self,
        claim_id: UUID,
        round_num: int,
        amount_inr: Decimal,
        expires_at_epoch: int,
        signature: str,
    ) -> bool:
        """
        Validates HMAC signature and checks TTL expiration.
        Returns True if valid, False if tampered or expired.
        """
        current_epoch = int(time.time())
        if current_epoch > expires_at_epoch:
            return False

        expected_signature = self.sign_offer(claim_id, round_num, amount_inr, expires_at_epoch)
        return hmac.compare_digest(expected_signature, signature)

    def generate_expiration_epoch(self, ttl_seconds: int = DEFAULT_OFFER_TTL_SECONDS) -> int:
        """Returns unix epoch timestamp for TTL expiration."""
        return int(time.time()) + ttl_seconds


hmac_offer_signer = HMACOfferSigner()

