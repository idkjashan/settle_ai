import asyncio
import hashlib
import time
import uuid
from pathlib import Path
from typing import Optional, List, Any, Union
from fastapi import UploadFile, BackgroundTasks
from app.core.config import settings
from app.core.exceptions import LockConflictException, AutoSettleException
from app.core.logging import logger
from app.domain.fast_fail_gate.schemas import (
    CaptureSource,
    CaptureModality,
    FastFailResponseDTO,
    FastFailTelemetryDTO,
    FastFailFailureCode,
    Tier1GateReport,
    ContainerGateReport,
    VisualGateReport,
    PhotoPackMetadataDTO,
    PhotoValidationReportDTO,
)
from app.domain.fast_fail_gate.policy_dedupe_gate import PolicyAndDedupeGate
from app.domain.fast_fail_gate.container_forensics import ContainerForensicsValidator
from app.domain.fast_fail_gate.visual_quality_gate import VisualQualityValidator
from app.domain.fast_fail_gate.remediation_mapper import RemediationMapper
from app.infrastructure.storage.scratch_ingest import ScratchIngestService, ScratchPhotoPackLease
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
        claim_description: Optional[str] = None,
        skip_stage_0: bool = False,
        skip_stage_1: bool = False,
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

            if not tier1_report.passed and not skip_stage_0:
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
            elif not tier1_report.passed and skip_stage_0:
                logger.info(f"[SKIP_STAGE_0] Bypassing Tier-1 policy check failure for claim {claim_id}")

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

            if tier2_codes and not skip_stage_0:
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
            elif tier2_codes and skip_stage_0:
                logger.info(f"[SKIP_STAGE_0] Bypassing Tier-2 media check failures for claim {claim_id}: {tier2_codes}")

            # Step 5: All Gates Passed!
            active_claim = Claim(
                claim_id=claim_id,
                policy_id=policy_id,
                video_sha256=lease.sha256_hex,
                capture_source=capture_source.value,
                is_demo_rehearsal=is_demo_rehearsal,
                claim_description=claim_description,
                current_stage="STAGE_1_IDENTITY",
                claim_status="PROCESSING",
                fast_fail_telemetry=telemetry.model_dump(),
            )
            await self.claim_repo.create_claim(active_claim)

            # ponytail: release in-flight lock AFTER claim insertion in PostgreSQL to eliminate TOCTOU window
            if not is_demo_rehearsal:
                await self.redis_mgr.release_video_lock(lease.sha256_hex)

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
                    import inspect
                    sig = inspect.signature(downstream_task)
                    if "skip_stage_1" in sig.parameters:
                        background_tasks.add_task(
                            downstream_task,
                            claim_id,
                            scratch_path,
                            policy_id,
                            is_demo_rehearsal,
                            claim_description,
                            skip_stage_1=skip_stage_1,
                        )
                    elif (
                        "claim_description" in sig.parameters
                        or len(sig.parameters) >= 5
                        or any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())
                    ):
                        background_tasks.add_task(
                            downstream_task, claim_id, scratch_path, policy_id, is_demo_rehearsal, claim_description
                        )
                    else:
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

    async def execute_photo_pack(
        self,
        claim_id: Optional[uuid.UUID] = None,
        policy_id: str = "",
        photo_paths: Optional[List[Any]] = None,
        is_demo_rehearsal: bool = False,
        background_tasks: Optional[BackgroundTasks] = None,
        downstream_task = None,
        claim_description: Optional[str] = None,
        capture_source: CaptureSource = CaptureSource.FILE_UPLOAD,
        skip_stage_0: bool = False,
        skip_stage_1: bool = False,
    ) -> FastFailResponseDTO:
        """
        Executes Stage 0 Fast-Fail Gates for a structured photo pack.
        Validates:
        - Tier-1: Policy validity and duplicate submission prevention
        - Tier-2: Photo count (3-6), file formats (JPEG/PNG), dimensions (>= 1080p),
                  sharpness (>= 60.0), and luminance ([45, 235])
        """
        t0 = time.perf_counter()

        # Handle flexible caller signatures: (claim_id, policy_id, photo_paths) vs (policy_id, photo_paths)
        if isinstance(claim_id, str) and (isinstance(policy_id, (list, tuple)) or policy_id is None):
            photo_paths = policy_id  # type: ignore
            policy_id = claim_id
            claim_id = uuid.uuid4()
        else:
            claim_id = claim_id or uuid.uuid4()

        photo_paths = photo_paths or []

        # Step 1: Ingest photo pack to scratch disk with incremental SHA-256
        if photo_paths and hasattr(photo_paths[0], "read"):
            # UploadFile instances from multipart form
            lease: ScratchPhotoPackLease = await self.ingest_service.stream_photo_pack_to_scratch(
                claim_id, photo_paths
            )
        else:
            # Existing Path instances on disk
            resolved_paths = [Path(p) for p in photo_paths]
            hasher = hashlib.sha256()
            total_bytes = 0
            for p in resolved_paths:
                if p.exists():
                    data = p.read_bytes()
                    hasher.update(data)
                    total_bytes += len(data)
            lease = ScratchPhotoPackLease(
                claim_id=claim_id,
                file_paths=resolved_paths,
                sha256_hex=hasher.hexdigest(),
                file_size_bytes=total_bytes,
            )

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
                    "A claim with this photo pack hash is currently processing. Concurrent duplicate blocked."
                )

        try:
            # Step 3: Tier-1 Policy & Historical Deduplication Gate
            tier1_report = await self.tier1_gate.validate(
                policy_id=policy_id,
                sha256_hex=lease.sha256_hex,
                is_demo_rehearsal=is_demo_rehearsal,
            )

            if not tier1_report.passed and not skip_stage_0:
                await self.redis_mgr.release_video_lock(lease.sha256_hex)
                lease.cleanup()

                telemetry = FastFailTelemetryDTO(
                    tier1_report=tier1_report,
                    capture_modality=CaptureModality.PHOTO_PACK,
                    total_execution_ms=(time.perf_counter() - t0) * 1000.0,
                )
                remediation = self.remediation_mapper.map_failures(
                    codes=tier1_report.failure_codes,
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
            elif not tier1_report.passed and skip_stage_0:
                logger.info(f"[SKIP_STAGE_0] Bypassing Tier-1 policy check failure for photo pack claim {claim_id}")

            # Step 4: Tier-2 Photo Pack Forensics (container metadata + visual quality)
            meta_report: PhotoPackMetadataDTO = await asyncio.to_thread(
                self.container_validator.validate_photo_pack,
                lease.file_paths,
            )
            visual_report: PhotoValidationReportDTO = await asyncio.to_thread(
                self.visual_validator.validate_photos,
                lease.file_paths,
            )

            tier2_codes: List[FastFailFailureCode] = list(meta_report.failure_codes) + list(visual_report.failure_codes)
            total_ms = (time.perf_counter() - t0) * 1000.0
            telemetry = FastFailTelemetryDTO(
                tier1_report=tier1_report,
                capture_modality=CaptureModality.PHOTO_PACK,
                photo_metadata_report=meta_report,
                photo_visual_report=visual_report,
                total_execution_ms=total_ms,
            )

            if tier2_codes and not skip_stage_0:
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
            elif tier2_codes and skip_stage_0:
                logger.info(f"[SKIP_STAGE_0] Bypassing Tier-2 photo pack check failures for claim {claim_id}: {tier2_codes}")

            # Step 5: All Gates Passed!
            active_claim = Claim(
                claim_id=claim_id,
                policy_id=policy_id,
                video_sha256=lease.sha256_hex,
                capture_source=capture_source.value,
                is_demo_rehearsal=is_demo_rehearsal,
                claim_description=claim_description,
                current_stage="STAGE_1_IDENTITY",
                claim_status="PROCESSING",
                fast_fail_telemetry=telemetry.model_dump(),
            )
            await self.claim_repo.create_claim(active_claim)

            if not is_demo_rehearsal:
                await self.redis_mgr.release_video_lock(lease.sha256_hex)

            # Publish SSE event
            await self.redis_mgr.publish_event(
                claim_id=claim_id,
                event_name="FAST_FAIL_GATE_PASSED",
                payload={
                    "claim_id": str(claim_id),
                    "status": "PROCESSING",
                    "stage": "STAGE_1_IDENTITY",
                    "modality": "PHOTO_PACK",
                },
            )

            # Transfer scratch file ownership to downstream
            scratch_paths = lease.transfer_to_downstream()

            # Dispatch background tasks
            if background_tasks:
                for idx, p in enumerate(scratch_paths):
                    background_tasks.add_task(
                        self.s3_client.upload_file, p, f"claims/{claim_id}/raw/photo_{idx}_{p.name}"
                    )
                if downstream_task:
                    import inspect
                    sig = inspect.signature(downstream_task)
                    if "skip_stage_1" in sig.parameters:
                        background_tasks.add_task(
                            downstream_task,
                            claim_id,
                            scratch_paths,
                            policy_id,
                            is_demo_rehearsal,
                            claim_description,
                            skip_stage_1=skip_stage_1,
                        )
                    elif (
                        "claim_description" in sig.parameters
                        or len(sig.parameters) >= 5
                        or any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())
                    ):
                        background_tasks.add_task(
                            downstream_task, claim_id, scratch_paths, policy_id, is_demo_rehearsal, claim_description
                        )
                    else:
                        background_tasks.add_task(downstream_task, claim_id, scratch_paths, policy_id, is_demo_rehearsal)

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

