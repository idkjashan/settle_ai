"""
app/domain/settlement_escalation/schemas.py
Pydantic v2 DTOs and Enums for Stage 6 Settlement Router & Escalation Dossier.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class ApportionedPartPayoutDTO(BaseModel):
    """Itemized cash-in-lieu allocation for a single damaged part committed to the ledger."""
    model_config = ConfigDict(frozen=True)

    canonical_part_key: str
    display_part_name: str
    damage_class: str
    gross_line_item_inr: Decimal
    apportioned_amount_inr: Decimal

    def to_dict(self, mode: str = "json") -> Dict[str, Any]:
        return self.model_dump(mode=mode)


class SettlementVoucherDTO(BaseModel):
    """Official digital cash-in-lieu settlement voucher and payout certificate."""
    model_config = ConfigDict(frozen=True)

    voucher_id: str
    claim_id: UUID
    policy_id: str
    registration_number: str
    vehicle_make_model: str
    settled_amount_inr: Decimal
    settled_amount_words: str
    beneficiary_upi_id: Optional[str] = None
    disbursement_ref: str
    apportioned_parts: List[ApportionedPartPayoutDTO]
    digital_signature_sha256: str
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self, mode: str = "json") -> Dict[str, Any]:
        return self.model_dump(mode=mode)


class HumanAdjusterDossierDTO(BaseModel):
    """Comprehensive claims investigation dossier for escalated claims."""
    model_config = ConfigDict(frozen=True)

    dossier_id: str
    claim_id: UUID
    policy_id: str
    registration_number: str
    escalation_code: str
    escalation_reason: str
    recommended_surveyor_action: str
    forensic_telemetry: Dict[str, Any]
    actuarial_summary: Optional[Dict[str, Any]] = None
    surveyor_checklist: List[str] = Field(default_factory=list)
    compiled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self, mode: str = "json") -> Dict[str, Any]:
        return self.model_dump(mode=mode)

