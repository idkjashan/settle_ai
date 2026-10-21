"""
app/domain/actuarial_pricing/enums.py
Domain enumerations for Stage 4 Actuarial Pricing Engine.
"""
from enum import Enum


class RepairAction(str, Enum):
    """Actuarial decision action for a damaged component."""
    REPAIR = "REPAIR"
    REPLACE = "REPLACE"


class MaterialType(str, Enum):
    """Material composition governing statutory depreciation and salvage rates."""
    METAL = "metal"
    PLASTIC = "plastic"
    RUBBER = "rubber"
    GLASS = "glass"
    FIBERGLASS = "fiberglass"
    ASSEMBLY = "assembly"


class PaintType(str, Enum):
    """Vehicle factory exterior finish type."""
    SOLID = "solid"
    METALLIC = "metallic"
    PEARL = "pearl"
    MATTE = "matte"


class DepreciationSchedule(str, Enum):
    """Statutory depreciation schedule category."""
    ZERO_DEP = "ZERO_DEP"
    IMT_STATUTORY_SCHEDULE = "IMT_STATUTORY_SCHEDULE"


class NCBRecommendation(str, Enum):
    """Advisory recommendation regarding No Claim Bonus economic utility."""
    PAY_OUT_OF_POCKET = "PAY_OUT_OF_POCKET"
    PROCEED_WITH_CLAIM = "PROCEED_WITH_CLAIM"


class ActuarialEscalationCode(str, Enum):
    """System-level escalation codes for Stage 4 pipeline gates."""
    ESC_03 = "ESC-03"  # Double dipping on unrepaired claim
    ESC_08 = "ESC-08"  # Autonomous financial ceiling exceeded (> ₹25,000.00)
    ESC_09 = "ESC-09"  # OEM catalogue part missing and no fallback available
