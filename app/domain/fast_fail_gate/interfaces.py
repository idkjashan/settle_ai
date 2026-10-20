from pathlib import Path
from typing import Protocol, List, Optional
import uuid
from app.domain.fast_fail_gate.schemas import (
    Tier1GateReport,
    ContainerGateReport,
    VisualGateReport,
    FastFailTelemetryDTO,
    FastFailResponseDTO,
    FastFailFailureCode,
    RemediationDirective,
    CaptureSource,
)

class IPolicyAndDedupeGate(Protocol):
    async def validate(self, policy_id: str, sha256_hex: str, is_demo_rehearsal: bool) -> Tier1GateReport:
        ...

class IContainerForensicsValidator(Protocol):
    def validate(self, video_path: Path, sha256: str, file_size_bytes: int) -> ContainerGateReport:
        ...

class IVisualQualityValidator(Protocol):
    def validate(self, video_path: Path, container_report: ContainerGateReport) -> VisualGateReport:
        ...

class IRemediationMapper(Protocol):
    def map_failures(
        self, codes: List[FastFailFailureCode], telemetry: Optional[FastFailTelemetryDTO]
    ) -> RemediationDirective:
        ...

