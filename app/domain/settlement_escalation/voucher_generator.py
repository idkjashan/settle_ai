"""
app/domain/settlement_escalation/voucher_generator.py
Constructs digital Settlement Vouchers with unique references, Indian currency words, and SHA-256 digital seals.
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import random
from typing import List, Optional
from uuid import UUID
from app.domain.actuarial_pricing.schemas import ActuarialEstimateDTO
from app.domain.settlement_escalation.schemas import (
    ApportionedPartPayoutDTO,
    SettlementVoucherDTO,
)


def number_to_indian_rupee_words(amount: Decimal) -> str:
    """Converts a Decimal currency amount into Indian English currency words."""
    units = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
             "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
             "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def _convert_below_thousand(n: int) -> str:
        res = ""
        if n >= 100:
            res += units[n // 100] + " Hundred "
            n %= 100
        if n >= 20:
            res += tens[n // 10] + " "
            n %= 10
        if n > 0:
            res += units[n] + " "
        return res.strip()

    total_paise = int(round(amount * 100))
    rupees = total_paise // 100
    paise = total_paise % 100

    if rupees == 0:
        words = "Zero Rupees"
    else:
        parts = []
        crores = rupees // 10000000
        rupees %= 10000000
        if crores > 0:
            parts.append(f"{_convert_below_thousand(crores)} Crore")

        lakhs = rupees // 100000
        rupees %= 100000
        if lakhs > 0:
            parts.append(f"{_convert_below_thousand(lakhs)} Lakh")

        thousands = rupees // 1000
        rupees %= 1000
        if thousands > 0:
            parts.append(f"{_convert_below_thousand(thousands)} Thousand")

        if rupees > 0:
            parts.append(_convert_below_thousand(rupees))

        words = " ".join(parts).strip() + " Rupees"

    if paise > 0:
        words += f" and {_convert_below_thousand(paise)} Paise"

    return words + " Only"


class SettlementVoucherGenerator:
    """
    Builds official Settlement Voucher DTOs with cryptographic integrity seals.
    """

    def generate_voucher(
        self,
        claim_id: UUID,
        policy_id: str,
        registration_number: str,
        vehicle_make_model: str,
        settled_amount_inr: Decimal,
        apportioned_parts: List[ApportionedPartPayoutDTO],
        beneficiary_upi_id: Optional[str] = None,
    ) -> SettlementVoucherDTO:
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        rand_suffix = f"{random.randint(100000, 999999)}"

        voucher_id = f"VOUCHER-AUTOSETTLE-{date_str}-{rand_suffix[:4]}"
        disbursement_ref = f"DISB-IMPS-{date_str}-{rand_suffix}"
        amount_words = number_to_indian_rupee_words(settled_amount_inr)

        # Generate SHA-256 digital certificate seal
        canonical_str = (
            f"VOUCHER_ID={voucher_id}|CLAIM_ID={claim_id}|REG={registration_number}|"
            f"AMOUNT={settled_amount_inr:.2f}|DISBURSEMENT_REF={disbursement_ref}|"
            f"ISSUED_AT={now.isoformat()}"
        )
        digital_seal = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

        return SettlementVoucherDTO(
            voucher_id=voucher_id,
            claim_id=claim_id,
            policy_id=policy_id,
            registration_number=registration_number,
            vehicle_make_model=vehicle_make_model,
            settled_amount_inr=settled_amount_inr,
            settled_amount_words=amount_words,
            beneficiary_upi_id=beneficiary_upi_id,
            disbursement_ref=disbursement_ref,
            apportioned_parts=apportioned_parts,
            digital_signature_sha256=digital_seal,
            issued_at=now,
        )


voucher_generator = SettlementVoucherGenerator()

