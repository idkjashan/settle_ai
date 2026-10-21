"""
app/domain/actuarial_pricing/exceptions.py
Exception hierarchy for Stage 4 Actuarial Pricing Engine.
"""
from typing import Any, Optional
from decimal import Decimal
from app.domain.actuarial_pricing.enums import ActuarialEscalationCode


class ActuarialPricingError(Exception):
    """Base exception for all actuarial pricing domain failures."""

    def __init__(
        self,
        message: str,
        escalation_code: Optional[ActuarialEscalationCode] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.escalation_code = escalation_code


class Stage4FinancialCeilingExceededError(ActuarialPricingError):
    """
    Raised when gross garage repair exceeds the autonomous limit of ₹25,000.00 (ESC-08).
    Optionally stores the preliminary ActuarialEstimateDTO computed prior to escalation.
    """

    def __init__(
        self,
        gross_amount_inr: str | Decimal = "25000.00",
        ceiling_inr: str | Decimal = "25000.00",
        preliminary_estimate: Optional[Any] = None,
        message: Optional[str] = None,
        estimate: Optional[Any] = None,
    ) -> None:
        gross_str = str(gross_amount_inr)
        ceiling_str = str(ceiling_inr)
        if message is not None:
            msg = message
        elif gross_str.startswith("ESC-"):
            msg = f"Autonomous financial ceiling exceeded ({gross_str}). Claim escalated to desk surveyor."
        else:
            msg = (
                f"Gross assessed repair amount of ₹{gross_str} exceeds the autonomous "
                f"cash-settlement ceiling of ₹{ceiling_str}. Claim escalated to desk surveyor."
            )
        super().__init__(msg, escalation_code=ActuarialEscalationCode.ESC_08)
        self.gross_amount_inr = gross_str
        self.ceiling_inr = ceiling_str
        stored_est = preliminary_estimate if preliminary_estimate is not None else estimate
        self.preliminary_estimate = stored_est
        self.estimate = stored_est


class Stage4DoubleDippingFraudError(ActuarialPricingError):
    """Raised when a verified damaged part has a prior unrepaired cash settlement (ESC-03)."""

    def __init__(
        self,
        registration_number: str = "",
        canonical_part_key: str = "",
        message: Optional[str] = None,
    ) -> None:
        if message:
            msg = message
            reg = registration_number
            part = canonical_part_key
        elif not canonical_part_key and (" " in registration_number or ":" in registration_number):
            msg = registration_number
            reg = ""
            part = ""
        else:
            reg = registration_number
            part = canonical_part_key
            msg = (
                f"Prior unrepaired cash-in-lieu settlement detected for vehicle {reg} "
                f"on part '{part}'. Re-claiming unrepaired damage is prohibited."
            )
        super().__init__(msg, escalation_code=ActuarialEscalationCode.ESC_03)
        self.registration_number = reg
        self.canonical_part_key = part


class Stage4CataloguePartNotFoundError(ActuarialPricingError):
    """Raised when an OEM part is missing from catalogue and no segment fallback exists (ESC-09)."""

    def __init__(
        self,
        make: str = "",
        model: str = "",
        canonical_part_key: str = "",
        message: Optional[str] = None,
    ) -> None:
        if message:
            msg = message
            m_make = make
            m_model = model
            m_part = canonical_part_key
        elif not model and not canonical_part_key and (" " in make or ":" in make):
            msg = make
            m_make = ""
            m_model = ""
            m_part = ""
        else:
            m_make = make
            m_model = model
            m_part = canonical_part_key
            msg = (
                f"Part record for '{m_part}' ({m_make} {m_model}) was not found in OEM "
                f"catalogue and no segment fallback is configured."
            )
        super().__init__(msg, escalation_code=ActuarialEscalationCode.ESC_09)
        self.make = m_make
        self.model = m_model
        self.canonical_part_key = m_part


class Stage4PolicyDataInvalidError(ActuarialPricingError):
    """Raised when required policy fields (manufacturing year, deductibles) are corrupt or missing."""

    def __init__(self, message: str = "Invalid or missing policy data.") -> None:
        super().__init__(message)
