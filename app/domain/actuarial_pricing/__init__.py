"""
app/domain/actuarial_pricing/__init__.py
Public API exports and clean facade for Stage 4 Actuarial Pricing Engine.
"""
from app.domain.actuarial_pricing.enums import (
    ActuarialEscalationCode,
    DepreciationSchedule,
    MaterialType,
    NCBRecommendation,
    PaintType,
    RepairAction,
)
from app.domain.actuarial_pricing.exceptions import (
    ActuarialPricingError,
    Stage4CataloguePartNotFoundError,
    Stage4DoubleDippingFraudError,
    Stage4FinancialCeilingExceededError,
    Stage4PolicyDataInvalidError,
)
from app.domain.actuarial_pricing.schemas import (
    ActuarialEstimateDTO,
    ActuarialLineItemDTO,
    ActuarialSummaryDTO,
    CashSettlementBandDTO,
    NCBAdvisoryDTO,
    PolicyPricingContextDTO,
)
from app.domain.actuarial_pricing.rules import (
    AUTONOMOUS_CEILING_INR,
    OVERLAP_DISCOUNT_FACTOR,
    STANDARD_GST_RATE,
    TWOPLACES,
    calculate_consumables_allowance,
    calculate_dent_labor_multiplier,
    calculate_denting_labor_multiplier,
    calculate_depreciation_rate,
    calculate_salvage_deduction,
    determine_repair_action,
    evaluate_repair_action,
    get_compulsory_excess_by_cc,
    get_imt_metal_depreciation_rate,
    get_paint_finish_multiplier,
    get_paint_type_multiplier,
    get_part_depreciation_rate,
    get_salvage_deduction_rate,
    quantize_inr,
    quantize_paisa,
    resolve_paint_overlap_factors,
)
from app.domain.actuarial_pricing.calculator import ActuarialCalculator
from app.domain.actuarial_pricing.ncb_advisor import NCBAdvisor
from app.domain.actuarial_pricing.orchestrator import Stage4ActuarialOrchestrator

# Domain aliases for public consumers
ActuarialPricingOrchestrator = Stage4ActuarialOrchestrator
ActuarialPricingEngine = Stage4ActuarialOrchestrator

__all__ = [
    # Enums
    "RepairAction",
    "MaterialType",
    "PaintType",
    "DepreciationSchedule",
    "NCBRecommendation",
    "ActuarialEscalationCode",
    # Exceptions
    "ActuarialPricingError",
    "Stage4FinancialCeilingExceededError",
    "Stage4DoubleDippingFraudError",
    "Stage4CataloguePartNotFoundError",
    "Stage4PolicyDataInvalidError",
    # Schemas
    "PolicyPricingContextDTO",
    "ActuarialLineItemDTO",
    "ActuarialSummaryDTO",
    "CashSettlementBandDTO",
    "NCBAdvisoryDTO",
    "ActuarialEstimateDTO",
    # Rules
    "quantize_inr",
    "quantize_paisa",
    "get_imt_metal_depreciation_rate",
    "get_part_depreciation_rate",
    "calculate_depreciation_rate",
    "get_paint_type_multiplier",
    "get_paint_finish_multiplier",
    "calculate_denting_labor_multiplier",
    "calculate_dent_labor_multiplier",
    "get_salvage_deduction_rate",
    "calculate_salvage_deduction",
    "determine_repair_action",
    "evaluate_repair_action",
    "resolve_paint_overlap_factors",
    "get_compulsory_excess_by_cc",
    "calculate_consumables_allowance",
    "TWOPLACES",
    "OVERLAP_DISCOUNT_FACTOR",
    "AUTONOMOUS_CEILING_INR",
    "STANDARD_GST_RATE",
    # Calculator & Advisor
    "ActuarialCalculator",
    "NCBAdvisor",
    # Orchestrator & Facades
    "Stage4ActuarialOrchestrator",
    "ActuarialPricingOrchestrator",
    "ActuarialPricingEngine",
]
