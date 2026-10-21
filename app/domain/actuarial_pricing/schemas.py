"""
app/domain/actuarial_pricing/schemas.py
Pydantic v2 DTOs for Stage 4 Actuarial Pricing Engine.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, field_validator
from app.domain.actuarial_pricing.enums import (
    RepairAction,
    MaterialType,
    PaintType,
    NCBRecommendation,
)


class PolicyPricingContextDTO(BaseModel):
    """Policy terms and vehicle context ingested by the pricing engine."""
    model_config = ConfigDict(frozen=True)

    policy_id: str
    registration_number: str
    make: str
    model: str
    manufacturing_year: int
    zero_dep_addon: bool = True
    paint_type: PaintType = PaintType.METALLIC
    compulsory_deductible_inr: Decimal = Decimal("1000.00")
    voluntary_deductible_inr: Decimal = Decimal("0.00")
    estimated_ncb_loss_inr: Decimal = Decimal("3200.00")
    engine_cc: Optional[int] = None

    @field_validator("paint_type", mode="before")
    @classmethod
    def normalize_paint_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v

    def to_dict(self, mode: str = "json") -> Dict[str, Any]:
        """Serialize DTO to dictionary."""
        return self.model_dump(mode=mode)


class ActuarialLineItemDTO(BaseModel):
    """Auditable, itemized financial calculation for a single damaged part."""
    model_config = ConfigDict(frozen=True)

    canonical_part_key: str
    display_part_name: str
    oem_part_number: str
    material: MaterialType
    action: RepairAction
    depth_grade: str
    iop_ratio: float

    # Parts Pricing
    base_part_cost_inr: Decimal
    depreciation_rate_pct: Decimal
    depreciation_amount_inr: Decimal
    net_part_cost_inr: Decimal
    salvage_deduction_inr: Decimal

    # Labor & Painting Pricing
    rr_labour_inr: Decimal
    denting_labour_inr: Decimal
    pdr_polish_flat_inr: Decimal
    base_paint_inr: Decimal
    paint_multiplier: Decimal
    paint_overlap_discount: Decimal
    final_paint_inr: Decimal

    # Line Item Aggregates
    pre_tax_total_inr: Decimal
    gst_amount_inr: Decimal
    gross_line_item_total_inr: Decimal

    @field_validator("material", mode="before")
    @classmethod
    def normalize_material(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.upper()
        return v

    @field_validator("depth_grade", mode="before")
    @classmethod
    def normalize_depth_grade(cls, v: Any) -> str:
        if hasattr(v, "value"):
            return str(v.value)
        return str(v)

    def to_dict(self, mode: str = "json") -> Dict[str, Any]:
        """Serialize DTO to dictionary."""
        return self.model_dump(mode=mode)


class ActuarialSummaryDTO(BaseModel):
    """Aggregated financial breakdown for the entire insurance claim."""
    model_config = ConfigDict(frozen=True)

    total_gross_parts_inr: Decimal
    total_depreciation_inr: Decimal
    total_net_parts_inr: Decimal
    total_labour_inr: Decimal
    total_paint_inr: Decimal
    pre_tax_subtotal_inr: Decimal
    total_gst_inr: Decimal
    gross_garage_repair_inr: Decimal
    total_salvage_deduction_inr: Decimal
    compulsory_deductible_inr: Decimal
    voluntary_deductible_inr: Decimal
    total_deductible_inr: Decimal
    net_claim_liability_inr: Decimal

    def to_dict(self, mode: str = "json") -> Dict[str, Any]:
        """Serialize DTO to dictionary."""
        return self.model_dump(mode=mode)


class CashSettlementBandDTO(BaseModel):
    """Algorithmic cash-in-lieu settlement band for Stage 5 negotiation."""
    model_config = ConfigDict(frozen=True)

    initial_offer_inr: Decimal = Field(description="O_0: 75% of net liability")
    target_settlement_inr: Decimal = Field(description="O_target: 85% of net liability")
    walkaway_cap_inr: Decimal = Field(description="O_max: min(₹25,000, 95% of net liability)")
    financial_ceiling_inr: Decimal = Decimal("25000.00")

    def to_dict(self, mode: str = "json") -> Dict[str, Any]:
        """Serialize DTO to dictionary."""
        return self.model_dump(mode=mode)


class NCBAdvisoryDTO(BaseModel):
    """No Claim Bonus economic utility assessment."""
    model_config = ConfigDict(frozen=True)

    recommendation: NCBRecommendation
    net_claim_liability_inr: Decimal
    estimated_ncb_loss_inr: Decimal
    net_benefit_inr: Decimal
    advisory_message: str

    def to_dict(self, mode: str = "json") -> Dict[str, Any]:
        """Serialize DTO to dictionary."""
        return self.model_dump(mode=mode)


class ActuarialEstimateDTO(BaseModel):
    """Master downstream DTO delivered to Stage 5 Chatbot and Stage 6 Settlement."""
    model_config = ConfigDict(frozen=True)

    claim_id: UUID
    policy_id: str
    registration_number: str
    vehicle_make: str
    vehicle_model: str
    vehicle_year: int
    calculation_timestamp: datetime
    is_zero_dep_active: bool
    is_ceiling_breached: bool = False
    escalation_code: Optional[str] = None
    line_items: List[ActuarialLineItemDTO]
    summary: ActuarialSummaryDTO
    settlement_band: CashSettlementBandDTO
    ncb_advisory: NCBAdvisoryDTO

    def to_dict(self, mode: str = "json") -> Dict[str, Any]:
        """Serialize DTO to dictionary for database persistence and JSON transmission."""
        return self.model_dump(mode=mode)
