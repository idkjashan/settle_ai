"""
app/domain/actuarial_pricing/interfaces.py
Typing protocols decoupling Stage 4 from direct database implementations and services.
"""
from typing import Protocol, Optional, List, Dict, Any, Tuple
from decimal import Decimal
from uuid import UUID
from app.infrastructure.db.models import InsuredPolicy, OemPart, UnrepairedClaim, Claim
from app.domain.actuarial_pricing.schemas import (
    PolicyPricingContextDTO,
    ActuarialLineItemDTO,
    ActuarialSummaryDTO,
    CashSettlementBandDTO,
    NCBAdvisoryDTO,
    ActuarialEstimateDTO,
)
from app.domain.vlm_damage_inspection.schemas import VerifiedDamagedPart


class IPolicyRepository(Protocol):
    """Protocol for policy underwriting data retrieval."""
    async def get_by_id(self, policy_id: str) -> Optional[InsuredPolicy]: ...
    async def get_by_registration(self, registration_number: str) -> Optional[InsuredPolicy]: ...


class IOemRepository(Protocol):
    """Protocol for OEM parts catalogue resolution and segment baselines."""
    async def get_part(self, make: str, model: str, canonical_part_key: str) -> Optional[OemPart]: ...
    async def get_segment_fallback(self, segment: str, canonical_part_key: str) -> Optional[Any]: ...


class IUnrepairedClaimsRepository(Protocol):
    """Protocol for unrepaired cash settlement fraud detection (ESC-03)."""
    async def get_unrepaired_claims(
        self, registration_number: str, canonical_part_keys: Optional[List[str]] = None
    ) -> List[UnrepairedClaim]: ...
    async def has_unrepaired_claim(
        self, registration_number: str, canonical_part_key: str
    ) -> bool: ...
    async def record_cash_payout(
        self,
        registration_number: str,
        canonical_part_key: str,
        damage_class: str,
        settled_amount: Decimal,
    ) -> UnrepairedClaim: ...


class IClaimRepository(Protocol):
    """Protocol for claim persistence and stage state transitions."""
    async def get_by_id(self, claim_id: UUID) -> Optional[Claim]: ...
    async def update_claim_stage(
        self,
        claim_id: UUID,
        stage: str,
        status: str,
        escalation_code: Optional[str] = None,
        failure_codes: Optional[List[str]] = None,
        telemetry_update: Optional[Dict[str, Any]] = None,
        telemetry_column: Optional[str] = None,
    ) -> Optional[Claim]: ...


class IActuarialCalculator(Protocol):
    """Protocol for deterministic actuarial calculation."""
    def calculate(
        self,
        policy_context: PolicyPricingContextDTO,
        verified_parts: List[VerifiedDamagedPart],
        oem_catalog: Dict[str, OemPart],
        current_year: int = 2026,
    ) -> Tuple[List[ActuarialLineItemDTO], ActuarialSummaryDTO, CashSettlementBandDTO]: ...


class INCBAdvisor(Protocol):
    """Protocol for No Claim Bonus economic utility assessment."""
    def evaluate(
        self,
        net_claim_liability_inr: Decimal,
        estimated_ncb_loss_inr: Decimal,
    ) -> NCBAdvisoryDTO: ...
