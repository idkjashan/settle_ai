import asyncio
import time
import uuid
from typing import Optional, List
from fastapi import UploadFile, BackgroundTasks
from app.core.config import settings
from app.core.exceptions import LockConflictException, AutoSettleException
from app.core.logging import logger
from app.domain.fast_fail_gate.schemas import (
    CaptureSource,
    FastFailResponseDTO,
    FastFailTelemetryDTO,
    FastFailFailureCode,
    Tier1GateReport,
    ContainerGateReport,
    VisualGateReport,
)
from app.domain.fast_fail_gate.policy_dedupe_gate import PolicyAndDedupeGate
from app.domain.fast_fail_gate.container_forensics import ContainerForensicsValidator
from app.domain.fast_fail_gate.visual_quality_gate import VisualQualityValidator
from app.domain.fast_fail_gate.remediation_mapper import RemediationMapper
from app.infrastructure.storage.scratch_ingest import ScratchIngestService
from app.infrastructure.storage.s3_client import S3Client
from app.infrastructure.cache.redis_manager import RedisManager
from app.infrastructure.db.repositories import ClaimRepository, PolicyRepository
from app.infrastructure.db.models import Claim

class FastFailGateOrchestrator:
    def __init__(
        self,
        ingest_service: ScratchIngestService,
        redis_mgr: RedisManager,
        tier1_gate: PolicyAndDedupeGate,
        container_validator: ContainerForensicsValidator,
        visual_validator: VisualQualityValidator,
        remediation_mapper: RemediationMapper,
        claim_repo: ClaimRepository,
        s3_client: S3Client,
    ):
        self.ingest_service = ingest_service
        self.redis_mgr = redis_mgr
        self.tier1_gate = tier1_gate
        self.container_validator = container_validator
        self.visual_validator = visual_validator
        self.remediation_mapper = remediation_mapper
        self.claim_repo = claim_repo
        self.s3_client = s3_client

    async def execute(
        self,
        policy_id: str,
        capture_source: CaptureSource,
        is_demo_rehearsal: bool,
        upload_file: UploadFile,
        background_tasks: Optional[BackgroundTasks] = None,
        claim_id: Optional[uuid.UUID] = None,
        downstream_task = None,
    ) -> FastFailResponseDTO:
        t0 = time.perf_counter()
        claim_id = claim_id or uuid.uuid4()

        # Step 1: Stream bytes to local scratch disk with incremental SHA-256
        lease = await self.ingest_service.stream_to_scratch(claim_id, upload_file)

        # Step 2: Atomic Redis In-Flight Lock (bypassed for demo rehearsal)
        if not is_demo_rehearsal:
            locked = await self.redis_mgr.acquire_video_lock(
                video_sha256=lease.sha256_hex,
                claim_id=claim_id,
                ttl_sec=settings.LOCK_TTL_SECONDS,
            )
            if not locked:
                lease.cleanup()
                raise LockConflictException(
                    "A claim with this video hash is currently processing. Concurrent duplicate blocked."
                )

        try:
            # Step 3: Tier-1 Policy & Historical Deduplication Gate
            tier1_report = await self.tier1_gate.validate(
                policy_id=policy_id,
                sha256_hex=lease.sha256_hex,
                is_demo_rehearsal=is_demo_rehearsal,
            )

            if not tier1_report.passed:
                # Short-circuit immediately (0% GPU, 0ms wasted on ffprobe/OpenCV)
                await self.redis_mgr.release_video_lock(lease.sha256_hex)
                lease.cleanup()

                telemetry = FastFailTelemetryDTO(
                    tier1_report=tier1_report,
                    container_report=None,
                    visual_report=None,
                    total_execution_ms=(time.perf_counter() - t0) * 1000.0,
                )
                remediation = self.remediation_mapper.map_failures(
                    codes=tier1_report.failure_codes,
                    telemetry=telemetry,
                )

                # Record rejected claim if policy exists
                try:
                    rejected_claim = Claim(
                        claim_id=claim_id,
                        policy_id=policy_id,
                        video_sha256=lease.sha256_hex,
                        capture_source=capture_source.value,
                        is_demo_rehearsal=is_demo_rehearsal,
                        current_stage="STAGE_0_SANITY",
                        claim_status="REJECTED_FAST_FAIL",
                        escalation_code="ESC-00",
                        failure_codes=[c.value for c in tier1_report.failure_codes],
                        fast_fail_telemetry=telemetry.model_dump(),
                    )
                    await self.claim_repo.create_claim(rejected_claim)
                except Exception as e:
                    logger.warning(f"Could not log rejected claim to DB: {e}")

                return FastFailResponseDTO(
                    passed=False,
                    claim_id=claim_id,
                    escalation_code="ESC-00",
                    failure_codes=tier1_report.failure_codes,
                    remediation=remediation,
                    telemetry=telemetry,
                )

            # Step 4: Tier-2 Media Forensic Gates (ffprobe + OpenCV in threadpool)
            container_report: ContainerGateReport = await asyncio.to_thread(
                self.container_validator.validate,
                lease.file_path,
                lease.sha256_hex,
                lease.file_size_bytes,
            )

            visual_report: Optional[VisualGateReport] = None
            tier2_codes: List[FastFailFailureCode] = list(container_report.failure_codes)

            if not container_report.passed and FastFailFailureCode.NO_VIDEO_STREAM in container_report.failure_codes:
                # Cannot run visual gate without a video stream
                pass
            else:
                visual_report = await asyncio.to_thread(
                    self.visual_validator.validate,
                    lease.file_path,
                    container_report,
                )
                tier2_codes.extend(visual_report.failure_codes)

            total_ms = (time.perf_counter() - t0) * 1000.0
            telemetry = FastFailTelemetryDTO(
                tier1_report=tier1_report,
                container_report=container_report,
                visual_report=visual_report,
                total_execution_ms=total_ms,
            )

            if tier2_codes:
                # Tier-2 failed
                await self.redis_mgr.release_video_lock(lease.sha256_hex)
                lease.cleanup()

                remediation = self.remediation_mapper.map_failures(
                    codes=tier2_codes,
                    telemetry=telemetry,
                )

                try:
                    rejected_claim = Claim(
                        claim_id=claim_id,
                        policy_id=policy_id,
                        video_sha256=lease.sha256_hex,
                        capture_source=capture_source.value,
                        is_demo_rehearsal=is_demo_rehearsal,
                        current_stage="STAGE_0_SANITY",
                        claim_status="REJECTED_FAST_FAIL",
                        escalation_code="ESC-00",
                        failure_codes=[c.value for c in tier2_codes],
                        fast_fail_telemetry=telemetry.model_dump(),
                    )
                    await self.claim_repo.create_claim(rejected_claim)
                except Exception as e:
                    logger.warning(f"Could not log rejected claim to DB: {e}")

                return FastFailResponseDTO(
                    passed=False,
                    claim_id=claim_id,
                    escalation_code="ESC-00",
                    failure_codes=tier2_codes,
                    remediation=remediation,
                    telemetry=telemetry,
                )

            # Step 5: All Gates Passed!
            if not is_demo_rehearsal:
                await self.redis_mgr.release_video_lock(lease.sha256_hex)

            active_claim = Claim(
                claim_id=claim_id,
                policy_id=policy_id,
                video_sha256=lease.sha256_hex,
                capture_source=capture_source.value,
                is_demo_rehearsal=is_demo_rehearsal,
                current_stage="STAGE_1_IDENTITY",
                claim_status="PROCESSING",
                fast_fail_telemetry=telemetry.model_dump(),
            )
            await self.claim_repo.create_claim(active_claim)

            # Publish SSE event
            await self.redis_mgr.publish_event(
                claim_id=claim_id,
                event_name="FAST_FAIL_GATE_PASSED",
                payload={"claim_id": str(claim_id), "status": "PROCESSING", "stage": "STAGE_1_IDENTITY"},
            )

            # Transfer scratch file ownership to downstream
            scratch_path = lease.transfer_to_downstream()

            # Dispatch background tasks
            s3_key = f"claims/{claim_id}/raw/walkaround.mp4"
            if background_tasks:
                background_tasks.add_task(self.s3_client.upload_file, scratch_path, s3_key)
                if downstream_task:
                    background_tasks.add_task(downstream_task, claim_id, scratch_path, policy_id, is_demo_rehearsal)

            return FastFailResponseDTO(
                passed=True,
                claim_id=claim_id,
                sse_stream_url=f"/api/v1/claims/{claim_id}/events",
                telemetry=telemetry,
            )

        except Exception:
            await self.redis_mgr.release_video_lock(lease.sha256_hex)
            lease.cleanup()
            raise

