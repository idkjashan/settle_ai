"""Forensic and operational domain exceptions for Stage 3 VLM Damage Inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID



class FailureCodeStr(str):
    """String subclass that allows transparent matching of hyphenated vs underscore escalation codes.

    E.g., "ESC-04_PREEXISTING_CORROSION" == "ESC_04_PREEXISTING_CORROSION".
    """
    def __eq__(self, other: object) -> bool:
        if super().__eq__(other):
            return True
        val = getattr(other, "value", other) if not isinstance(other, str) else other
        if isinstance(val, str):
            return self.replace("-", "_") == val.replace("-", "_")
        return False

    def __hash__(self) -> int:
        return hash(self.replace("-", "_"))

class Stage3InspectionError(Exception):
    """Base exception for all Stage 3 VLM damage inspection errors."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# Alias for backward compatibility
Stage3BaseException = Stage3InspectionError


class Stage3RustOrOxidationError(Stage3InspectionError):
    """Raised when pre-existing rust or oxidation ($Fe_2O_3$) is identified inside damage boundary (ESC-04)."""
    def __init__(
        self,
        message: str,
        part_key: str,
        claim_id: Optional[UUID | str] = None,
        evidence_path: Optional[Path | str] = None,
    ):
        super().__init__(message)
        self.escalation_code = "ESC-04"
        self.failure_code = FailureCodeStr("ESC-04_PREEXISTING_CORROSION")
        self.part_key = part_key
        self.claim_id = claim_id
        self.evidence_path = Path(evidence_path) if evidence_path else None


class Stage3StructuralMisalignmentError(Stage3InspectionError):
    """Raised when structural frame shift or panel seam wedging/pinching is detected (ESC-06)."""
    def __init__(
        self,
        message: str,
        part_key: str,
        claim_id: Optional[UUID | str] = None,
        evidence_path: Optional[Path | str] = None,
    ):
        super().__init__(message)
        self.escalation_code = "ESC-06"
        self.failure_code = FailureCodeStr("ESC-06_STRUCTURAL_HAZARD")
        self.part_key = part_key
        self.claim_id = claim_id
        self.evidence_path = Path(evidence_path) if evidence_path else None


class Stage3NoRealDamageDetectedError(Stage3InspectionError):
    """Raised when all candidate damage marks are dismissed as superficial non-damage deposits (ESC-07)."""
    def __init__(
        self,
        message: str,
        claim_id: Optional[UUID | str] = None,
        dismissed_summary: Optional[List[Dict[str, Any]]] = None,
    ):
        super().__init__(message)
        self.escalation_code = "ESC-07"
        self.failure_code = FailureCodeStr("ESC-07_NO_REAL_DAMAGE_DETECTED")
        self.claim_id = claim_id
        self.dismissed_summary = dismissed_summary or []


class Stage3ProviderUnreachableError(Stage3InspectionError):
    """Raised when a vision provider endpoint cannot be reached or times out."""
    def __init__(self, message: str, provider: Optional[str] = None):
        super().__init__(message)
        self.provider = provider
        self.failure_code = "S3_PROVIDER_UNREACHABLE"


class Stage3MalformedOutputError(Stage3InspectionError):
    """Raised when VLM output fails schema validation, codefence stripping, or JSON decoding."""
    def __init__(self, message: str, raw_output: Optional[str] = None):
        super().__init__(message)
        self.raw_output = raw_output
        self.failure_code = "S3_MALFORMED_OUTPUT"


class Stage3CircuitBreakerOpenError(Stage3InspectionError):
    """Raised when incoming requests are rejected because the circuit breaker is in OPEN state."""
    def __init__(self, message: str = "VLM Provider Circuit Breaker is OPEN. Downstream calls blocked."):
        super().__init__(message)
        self.failure_code = "S3_PROVIDER_UNREACHABLE"


# LLD-compatible aliases
Stage3OutputParsingError = Stage3MalformedOutputError
Stage3InfrastructureError = Stage3ProviderUnreachableError
