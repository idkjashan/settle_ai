"""Stage 3: Set-of-Marks (SoM) VLM Damage Inspection Module.

Establishes objective physical ground truth regarding vehicle damage, 5-grade depth severity,
pre-existing corrosion (ESC-04), and structural frame misalignment (ESC-06).
"""

from __future__ import annotations

from app.domain.vlm_damage_inspection.adapters import (
    DeterministicMockVLMAdapter,
    GeminiVisionAdapter,
    IVLMInspectionAdapter,
    OllamaVisionAdapter,
    OpenAIVisionAdapter,
    VLMProviderFactory,
    get_vlm_adapter,
)
from app.domain.vlm_damage_inspection.circuit_breaker import (
    CircuitBreaker,
    execute_with_jitter_retry,
)
from app.domain.vlm_damage_inspection.config import Stage3Settings, stage3_settings
from app.domain.vlm_damage_inspection.exceptions import (
    Stage3BaseException,
    Stage3CircuitBreakerOpenError,
    Stage3InfrastructureError,
    Stage3InspectionError,
    Stage3MalformedOutputError,
    Stage3NoRealDamageDetectedError,
    Stage3OutputParsingError,
    Stage3ProviderUnreachableError,
    Stage3RustOrOxidationError,
    Stage3StructuralMisalignmentError,
)
from app.domain.vlm_damage_inspection.forensic_engine import ForensicDecisionEngine
from app.domain.vlm_damage_inspection.network_utils import (
    is_port_open,
    resolve_ollama_url,
    resolve_wsl2_gateway,
)
from app.domain.vlm_damage_inspection.orchestrator import Stage3VLMOrchestrator
from app.domain.vlm_damage_inspection.prompt_engine import VLMPromptEngine
from app.domain.vlm_damage_inspection.prompts import SYSTEM_PROMPT, build_user_prompt
from app.domain.vlm_damage_inspection.resilient_parser import ResilientJSONParser
from app.domain.vlm_damage_inspection.schemas import (
    DepthGrade,
    FalsePositiveReason,
    InspectionContext,
    InspectionCropPair,
    QuarantinedPartRecord,
    Stage3FailureCode,
    Stage3Telemetry,
    Stage4HandoffPayload,
    VerifiedDamagedPart,
    VLMInspectionOutput,
    VLMProviderType,
)

__all__ = [
    # Orchestrator & Engines
    "Stage3VLMOrchestrator",
    "ForensicDecisionEngine",
    "VLMPromptEngine",
    # Schemas & Enums
    "DepthGrade",
    "FalsePositiveReason",
    "Stage3FailureCode",
    "VLMProviderType",
    "InspectionContext",
    "InspectionCropPair",
    "VLMInspectionOutput",
    "VerifiedDamagedPart",
    "QuarantinedPartRecord",
    "Stage4HandoffPayload",
    "Stage3Telemetry",
    # Configuration
    "Stage3Settings",
    "stage3_settings",
    # Exceptions
    "Stage3InspectionError",
    "Stage3BaseException",
    "Stage3RustOrOxidationError",
    "Stage3StructuralMisalignmentError",
    "Stage3NoRealDamageDetectedError",
    "Stage3ProviderUnreachableError",
    "Stage3MalformedOutputError",
    "Stage3CircuitBreakerOpenError",
    "Stage3OutputParsingError",
    "Stage3InfrastructureError",
    # Resilience & Parser
    "CircuitBreaker",
    "execute_with_jitter_retry",
    "ResilientJSONParser",
    # Network Utils
    "resolve_wsl2_gateway",
    "resolve_ollama_url",
    "is_port_open",
    # Prompts
    "SYSTEM_PROMPT",
    "build_user_prompt",
    # Adapters & Factory
    "IVLMInspectionAdapter",
    "DeterministicMockVLMAdapter",
    "OllamaVisionAdapter",
    "GeminiVisionAdapter",
    "OpenAIVisionAdapter",
    "get_vlm_adapter",
    "VLMProviderFactory",
]
