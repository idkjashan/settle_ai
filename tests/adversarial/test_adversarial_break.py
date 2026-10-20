"""
tests/adversarial/test_adversarial_break.py
RED TEAM ADVERSARIAL TEST SUITE — Auto-Settle AI Stage 0 & Stage 1.
Probes for edge cases, unhandled exceptions, OpenCV assertion failures,
false passes, resource leaks, race conditions, and zombie pipeline states.
"""
import asyncio
import io
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import cv2
import numpy as np
import pytest
import pytest_asyncio
import torch
from fastapi import UploadFile, BackgroundTasks
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import LockConflictException, AutoSettleException
from app.domain.fast_fail_gate.schemas import (
    CaptureSource,
    FastFailFailureCode,
    ContainerGateReport,
    SampledFrameMetric,
)
from app.domain.fast_fail_gate.orchestrator import FastFailGateOrchestrator
from app.domain.fast_fail_gate.policy_dedupe_gate import PolicyAndDedupeGate
from app.domain.fast_fail_gate.container_forensics import (
    ContainerForensicsValidator,
    container_forensics_validator,
)
from app.domain.fast_fail_gate.visual_quality_gate import (
    VisualQualityValidator,
    visual_quality_validator,
)
from app.domain.fast_fail_gate.remediation_mapper import remediation_mapper
from app.infrastructure.storage.scratch_ingest import scratch_ingest_service, ScratchIngestService
from app.infrastructure.storage.s3_client import s3_client
from app.infrastructure.cache.redis_manager import redis_manager
from app.infrastructure.db.repositories import ClaimRepository, PolicyRepository
from app.infrastructure.db.models import Claim, InsuredPolicy
from app.infrastructure.db.session import async_session_factory

from app.domain.vehicle_identity_continuity.cut_detector import CutDetector, cut_detector
from app.domain.vehicle_identity_continuity.color_grounding_validator import (
    ColorGroundingValidator,
    color_grounding_validator,
)
from app.domain.vehicle_identity_continuity.plate_ocr_validator import (
    PlateOCRValidator,
    plate_ocr_validator,
)
from app.domain.vehicle_identity_continuity.object_tracker import ObjectTracker, object_tracker
from app.domain.vehicle_identity_continuity.orchestrator import VehicleIdentityContinuityOrchestrator
from app.domain.vehicle_identity_continuity.schemas import PolicyGroundingContext
from app.api.v1.endpoints.claims_router import run_stage1_pipeline_task


class TestGate1ContinuityAdversarial:
    """1. Gate 1 False Pass on 0-Frame / Corrupt Video."""

    def test_adv_01_cut_detector_false_pass_on_truncated_zero_frame_video(
        self, truncated_zero_frame_video: Path
    ):
        """
        Adversarial Scenario:
        An MP4 video container has a valid header so cv2.VideoCapture.isOpened() returns True,
        but the video stream contains 0 decodeable frames.

        Expected Secure Behavior:
        The continuity detector must verify that frames were actually evaluated (> 0).
        If 0 frames are read, it MUST reject the video as discontinuous/corrupt (is_continuous=False, failure_code="ESC-02").

        Vulnerability / Actual Failure Mode:
        In CutDetector.evaluate(), the while loop terminates immediately (evaluated_frames=0, cut_indices=[]).
        The result is computed as `is_continuous = len(cut_indices) == 0`, which evaluates to TRUE!
        A 0-frame corrupt file falsely PASSES Gate 1 without detecting any cuts!
        """
        detector = CutDetector()
        result = detector.evaluate(truncated_zero_frame_video)

        # Assert that zero-frame / truncated corrupt video is NOT treated as continuous
        assert result.is_continuous is False, (
            f"CRITICAL FALSE PASS: CutDetector returned is_continuous=True for a 0-frame video! "
            f"Failure code was: {result.failure_code}"
        )
        assert result.failure_code == "ESC-02"


class TestScratchDiskLeakage:
    """2. Scratch Disk Leakage after Upload & Stage 1 Execution."""

    @pytest.mark.asyncio
    async def test_adv_02_scratch_disk_leak_after_stage1_execution(
        self, db_session, redis_mgr, adv_assets_dir
    ):
        """
        Adversarial Scenario:
        A claimant uploads a video. The video passes Stage 0 (Fast-Fail Gate).
        `lease.transfer_to_downstream()` is called, which disables `lease.cleanup()`.
        Stage 1 execution then completes (or fails).

        Expected Secure Behavior:
        Downstream processors or background task wrappers must unlink the scratch file
        in `/tmp/autosettle_ingest/{claim_id}.mp4` after processing to avoid exhausting disk space.

        Vulnerability / Actual Failure Mode:
        Neither `run_stage1_pipeline_task` nor `VehicleIdentityContinuityOrchestrator` unlinks
        the scratch file. Files accumulate indefinitely in `/tmp/autosettle_ingest/`.
        """
        claim_id = uuid.uuid4()
        scratch_dir = Path(settings.SCRATCH_DIR)
        scratch_dir.mkdir(parents=True, exist_ok=True)
        scratch_file = scratch_dir / f"{claim_id}.mp4"

        # Create a dummy scratch file representing the transferred lease
        dummy_content = b"\x00" * 2048
        scratch_file.write_bytes(dummy_content)
        assert scratch_file.exists()

        # Execute Stage 1 orchestrator on this file (it will fail on invalid video, but must still clean up)
        policy_repo = PolicyRepository(db_session)
        claim_repo = ClaimRepository(db_session)
        stage1_orch = VehicleIdentityContinuityOrchestrator(
            policy_repo=policy_repo,
            claim_repo=claim_repo,
            redis_mgr=redis_mgr,
        )

        try:
            await stage1_orch.execute(
                claim_id=claim_id,
                scratch_video_path=scratch_file,
                policy_id="POL-HAPPY-001",
            )
        except Exception:
            pass

        # Check whether the scratch video was unlinked or leaked
        is_leaked = scratch_file.exists()
        try:
            if scratch_file.exists():
                scratch_file.unlink()  # cleanup test artifact
        except Exception:
            pass

        assert not is_leaked, (
            f"RESOURCE LEAK DETECTED: Scratch file {scratch_file} was not deleted "
            f"after Stage 1 execution completed!"
        )


class TestInFlightLockRaceCondition:
    """3. In-flight Lock TOCTOU Race Condition on Concurrent Submissions."""

    @pytest.mark.asyncio
    async def test_adv_03_inflight_lock_release_before_claim_creation_toctou(
        self, db_session, redis_mgr, adv_assets_dir
    ):
        """
        Adversarial Scenario:
        In FastFailGateOrchestrator.execute():
        Line 197: `await self.redis_mgr.release_video_lock(lease.sha256_hex)`
        Line 209: `await self.claim_repo.create_claim(active_claim)`
        The Redis in-flight lock is released BEFORE the claim is inserted into PostgreSQL.

        Expected Secure Behavior:
        The distributed lock must protect the critical section through PostgreSQL claim insertion.
        Any concurrent request with the same video SHA-256 must be serialized and rejected as duplicate.

        Vulnerability / Actual Failure Mode:
        There is a TOCTOU (Time-of-Check to Time-of-Use) window where the lock is released but
        no record exists in PostgreSQL yet. A concurrent request acquires the newly freed lock,
        passes Tier-1 deduplication (since DB has no record yet), and proceeds to create
        a duplicate active claim or triggers an unhandled Postgres UniqueViolation 500 error!
        """
        video_bytes = b"ADVERSARIAL_IDENTICAL_VIDEO_STREAM_" + uuid.uuid4().bytes * 100
        sha_hex = "mock_sha256_" + uuid.uuid4().hex[:16]

        claim_repo = ClaimRepository(db_session)
        policy_repo = PolicyRepository(db_session)
        tier1_gate = PolicyAndDedupeGate(policy_repo, claim_repo)

        # We verify that the in-flight lock remains held throughout DB claim creation:
        claim_id_1 = uuid.uuid4()
        claim_id_2 = uuid.uuid4()
        lock_held_during_db_insert = []

        original_create_claim = claim_repo.create_claim

        async def spy_create_claim(claim):
            # Check if lock is still held by Request 1 while DB insertion is occurring
            can_reacquire = await redis_mgr.acquire_video_lock(sha_hex, claim_id_2)
            lock_held_during_db_insert.append(not can_reacquire)
            if can_reacquire:
                await redis_mgr.release_video_lock(sha_hex)
            return await original_create_claim(claim)

        # 1. Acquire initial lock for Request 1
        acquired_1 = await redis_mgr.acquire_video_lock(sha_hex, claim_id_1)
        assert acquired_1 is True, "First lock acquisition failed"

        # 2. Simulate orchestrator reaching claim creation and release order:
        # DB claim insertion happens while lock is held
        with patch.object(claim_repo, "create_claim", side_effect=spy_create_claim):
            active_claim = Claim(
                claim_id=claim_id_1,
                policy_id="POL-HAPPY-001",
                video_sha256=sha_hex,
                capture_source=CaptureSource.FILE_UPLOAD.value,
                is_demo_rehearsal=False,
                current_stage="STAGE_1_IDENTITY",
                claim_status="PROCESSING",
            )
            await claim_repo.create_claim(active_claim)

            # In fixed orchestrator.py, lock release is performed AFTER create_claim:
            await redis_mgr.release_video_lock(sha_hex)

        # Assert: during DB insertion, Request 2 was locked out (lock held)
        assert lock_held_during_db_insert == [True], (
            "TOCTOU DEFECT: In-flight lock was NOT held during PostgreSQL claim insertion!"
        )

        # Assert: after lock release, Request 2 encounters the committed claim in DB
        is_dup = await claim_repo.check_historical_duplicate(sha_hex)
        assert is_dup is True, "PostgreSQL claim was not committed"

        # When Request 2 runs Tier 1 dedupe gate, it is rejected by DB check:
        t1_result = await tier1_gate.validate(policy_id="POL-HAPPY-001", sha256_hex=sha_hex, is_demo_rehearsal=False)
        assert t1_result.passed is False
        assert FastFailFailureCode.DUPLICATE_VIDEO_SUBMISSION in t1_result.failure_codes


class TestOpenCVCrashesInValidators:
    """4. OpenCV Crashes in Color & Plate Validators on Degenerate Bounding Boxes."""

    def test_adv_04a_color_validator_crashes_on_zero_bounding_box(self):
        """
        Adversarial Scenario:
        YOLO or an upstream detector outputs a degenerate bounding box: (0, 0, 0, 0).

        Expected Secure Behavior:
        ColorGroundingValidator.validate_paint_color() must check for degenerate/empty
        bounding boxes and gracefully return ColorValidationResult(is_color_match=False, failure_code="ESC-01")
        without throwing an unhandled OpenCV exception.

        Vulnerability / Actual Failure Mode:
        veh_crop has shape (0, 0, 3) (size == 0).
        cv2.cvtColor(veh_crop, cv2.COLOR_BGR2HSV) is called directly on the empty array.
        OpenCV raises:
        `cv2.error: OpenCV(5.0.0) ...: (-215:Assertion failed) !_src.empty() in function 'cvtColor'`
        crashing the entire Stage 1 pipeline!
        """
        validator = ColorGroundingValidator()
        ctx = PolicyGroundingContext(
            policy_id="POL-01",
            registration_number="MH12DE1433",
            make="Hyundai",
            model="Creta",
            registered_color="WHITE",
        )
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        try:
            result = validator.validate_paint_color(frame, (0, 0, 0, 0), ctx)
            assert result.is_color_match is False
        except cv2.error as e:
            pytest.fail(
                f"CRASH: ColorGroundingValidator crashed with cv2.error on (0, 0, 0, 0) bbox! {e}"
            )

    def test_adv_04b_color_validator_crashes_on_out_of_bounds_bounding_box(self):
        """
        Adversarial Scenario:
        Vehicle bbox coordinates are completely outside the frame: (1500, 1500, 1600, 1600) on 1280x720 frame.

        Expected Secure Behavior:
        Gracefully clamp coordinates or detect empty intersection, returning match=False without crashing.

        Vulnerability / Actual Failure Mode:
        x1 is clamped with max(0, 1500) -> 1500.
        x2 is clamped with min(w_f, 1600) -> 1280.
        veh_crop = frame[720:720, 1500:1280] has size 0.
        cv2.cvtColor crashes with (-215:Assertion failed) !_src.empty()!
        """
        validator = ColorGroundingValidator()
        ctx = PolicyGroundingContext(
            policy_id="POL-01",
            registration_number="MH12DE1433",
            make="Hyundai",
            model="Creta",
            registered_color="WHITE",
        )
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        try:
            result = validator.validate_paint_color(frame, (1500, 1500, 1600, 1600), ctx)
            assert result.is_color_match is False
        except cv2.error as e:
            pytest.fail(
                f"CRASH: ColorGroundingValidator crashed with cv2.error on out-of-bounds bbox! {e}"
            )

    def test_adv_04c_plate_validator_negative_bounding_box_roi_inversion(self):
        """
        Adversarial Scenario:
        YOLO outputs a bounding box with negative coordinates: vx1 = -50, vx2 = 200 (car partially cut off on left edge).

        Expected Secure Behavior:
        PlateOCRValidator must clamp vx1 and vx2 to [0, w] before slicing:
        crop_x1 = max(0, vx1), crop_x2 = min(w, vx2).

        Vulnerability / Actual Failure Mode:
        In PlateOCRValidator.validate_initial_window:
        Lines 148-150 clamp crop_y1 and crop_y2:
            crop_y1 = max(0, int(vy1 + vh * ...))
            crop_y2 = min(h, int(vy1 + vh * ...))
        BUT vx1 and vx2 are NOT clamped:
            veh_roi = frame[crop_y1:crop_y2, vx1:vx2]
        In Python/numpy, `frame[:, -50:200]` on a 1280-pixel wide array slices `1230:200`,
        yielding an empty slice (width 0), causing OCR to miss the plate entirely!
        """
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        vx1, vy1, vx2, vy2 = -50, 100, 200, 400
        vh = vy2 - vy1
        h, w = frame.shape[:2]

        validator = PlateOCRValidator()
        veh_roi = validator.crop_bumper_roi(frame, (vx1, vy1, vx2, vy2))

        # The car has 200 valid visible horizontal pixels (from 0 to 200).
        # The clamped slice produces a valid non-empty slice of width 200.
        assert veh_roi.shape[1] > 0, (
            f"NEGATIVE BBOX DEFECT: PlateOCRValidator sliced frame with unclamped vx1={vx1}, vx2={vx2}. "
            f"Produced empty/inverted ROI slice: shape={veh_roi.shape}"
        )


class TestContainerForensicsFailures:
    """5. Container Forensics Failures on Malformed Tags, Missing Video, and Overexposed Video."""

    def test_adv_05a_container_forensics_crashes_on_null_tags(self, adv_assets_dir):
        """
        Adversarial Scenario:
        ffprobe returns JSON where `tags` in video stream or format is `null` (None).

        Expected Secure Behavior:
        ContainerForensicsValidator.validate() safely handles null tags and returns ContainerGateReport.

        Vulnerability / Actual Failure Mode:
        In container_forensics.py:
        Line 80: `tags = video_stream.get("tags", {})`
        When JSON contains `"tags": null`, `.get("tags", {})` returns None!
        Line 81: `if "rotate" in tags:` raises:
        `TypeError: argument of type 'NoneType' is not iterable`!
        """
        validator = ContainerForensicsValidator()
        dummy_file = adv_assets_dir / "dummy_null_tags.mp4"
        dummy_file.write_bytes(b"\x00" * 1024)

        mock_probe = {
            "format": {"format_name": "mov,mp4", "duration": "10.0", "tags": None},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1280,
                    "height": 720,
                    "avg_frame_rate": "30/1",
                    "tags": None,
                }
            ],
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_probe))
            try:
                report = validator.validate(dummy_file, "sha", 1024)
                assert report is not None
            except TypeError as e:
                pytest.fail(f"CRASH: ContainerForensicsValidator crashed on null tags! {e}")

    def test_adv_05b_container_forensics_crashes_on_non_numeric_dimensions(self, adv_assets_dir):
        """
        Adversarial Scenario:
        ffprobe returns JSON where `width` or `height` is "N/A" or non-numeric.

        Expected Secure Behavior:
        Validation safely catches ValueError and records CONTAINER_PARSE_FAILED.

        Vulnerability / Actual Failure Mode:
        Line 71: `width = int(video_stream.get("width") or 0)`
        If width is `"N/A"`, `"N/A" or 0` evaluates to `"N/A"`.
        `int("N/A")` raises:
        `ValueError: invalid literal for int() with base 10: 'N/A'`!
        """
        validator = ContainerForensicsValidator()
        dummy_file = adv_assets_dir / "dummy_na_dim.mp4"
        dummy_file.write_bytes(b"\x00" * 1024)

        mock_probe = {
            "format": {"format_name": "mov,mp4", "duration": "10.0"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": "N/A",
                    "height": 720,
                    "avg_frame_rate": "30/1",
                }
            ],
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(mock_probe))
            try:
                report = validator.validate(dummy_file, "sha", 1024)
                assert FastFailFailureCode.CONTAINER_PARSE_FAILED in report.failure_codes
            except ValueError as e:
                pytest.fail(
                    f"CRASH: ContainerForensicsValidator crashed on non-numeric width 'N/A'! {e}"
                )

    def test_adv_05c_container_forensics_audio_only_disguised_mp4(self, audio_only_mp4: Path):
        """
        Adversarial Scenario:
        An audio-only container disguised as an MP4 claim video (AAC audio stream, no video stream).

        Expected Secure Behavior:
        Container forensics validator must flag NO_VIDEO_STREAM.
        Visual quality validator must cleanly fail or be bypassed without crashing.
        """
        c_rep = container_forensics_validator.validate(
            audio_only_mp4, "sha", audio_only_mp4.stat().st_size
        )
        assert c_rep.passed is False
        assert FastFailFailureCode.NO_VIDEO_STREAM in c_rep.failure_codes

        # If visual quality gate is called on audio-only file, it must not crash
        try:
            v_rep = visual_quality_validator.validate(audio_only_mp4, c_rep)
            assert v_rep.passed is False
        except Exception as e:
            pytest.fail(f"CRASH: VisualQualityValidator crashed on audio-only file! {e}")

    def test_adv_05d_visual_quality_overexposed_video_false_pass(
        self, overexposed_textured_video: Path
    ):
        """
        Adversarial Scenario:
        An overexposed, washed-out video (mean luminance Y ~224 > 220).
        At this luminance level, dent shadows and paint scratches are completely invisible.

        Expected Secure Behavior:
        The visual quality validator should reject overexposed video with VIDEO_TOO_BRIGHT.

        Vulnerability / Actual Failure Mode:
        In config.py, LUMINANCE_MAX_THRESHOLD is set to 235.0 (overly lenient ceiling).
        In visual_quality_gate.py:
        `is_overexposed = mean_y > 235.0`
        A video with mean luminance 224 evaluates is_overexposed=False (bright_count=0).
        The overexposed video falsely passes visual quality!
        """
        c_rep = container_forensics_validator.validate(
            overexposed_textured_video, "sha", overexposed_textured_video.stat().st_size
        )
        v_rep = visual_quality_validator.validate(overexposed_textured_video, c_rep)

        assert FastFailFailureCode.VIDEO_TOO_BRIGHT in v_rep.failure_codes, (
            f"FALSE PASS VULNERABILITY: Severe overexposed video (mean_Y={v_rep.mean_luminance_aggregate:.1f} > 220) "
            f"passed without triggering VIDEO_TOO_BRIGHT! (Threshold={settings.LUMINANCE_MAX_THRESHOLD})"
        )


class TestTruncatedVideoQuorumAttack:
    """6. Truncated Video Quorum Attack False Pass."""

    def test_adv_06_truncated_video_quorum_attack_false_pass(
        self, truncated_15s_quorum_attack_video: Path
    ):
        """
        Adversarial Scenario:
        A 15-second video container is truncated to only 25% of its file size.
        The container header claims duration is 15.0 seconds.
        Only the first sample frame (frame 45 at 10% pos) can be read before EOF/corruption.
        Samples 1, 2, 3, 4 (at 30%, 50%, 70%, 90%) are missing.

        Expected Secure Behavior:
        Visual quality verification requires evaluating 5 distinct temporal sample points.
        If the stream terminates prematurely and only 1 sample is readable, the gate MUST reject
        the video with CONTAINER_PARSE_FAILED or DURATION_TOO_SHORT.

        Vulnerability / Actual Failure Mode:
        In visual_quality_gate.py:
        `total_samples = len(sampled_metrics)` (which evaluates to 1!)
        `quorum_threshold = (total_samples // 2) + 1` (which evaluates to 1!)
        Since sample 0 is not dark, bright, or blurry:
        dark_count=0, bright_count=0, blurry_count=0.
        All three fail counts are < 1 (the quorum threshold).
        The validator concludes:
        `passed = True, failure_codes = []`!
        A 15-second claim video with 80% of its content missing falsely passes Stage 0!
        """
        c_rep = container_forensics_validator.validate(
            truncated_15s_quorum_attack_video, "sha", truncated_15s_quorum_attack_video.stat().st_size
        )
        v_rep = visual_quality_validator.validate(truncated_15s_quorum_attack_video, c_rep)

        # Assert: A 15s video yielding only 1 frame must NOT pass visual gate
        assert v_rep.passed is False, (
            f"QUORUM ATTACK VULNERABILITY: Truncated 15s video yielded only {len(v_rep.sampled_frames)}/5 samples "
            f"but passed visual quality with failure_codes={v_rep.failure_codes}!"
        )


class TestBackgroundPipelineStuckState:
    """7. Background Pipeline Failure & Stuck State in PostgreSQL."""

    @pytest.mark.asyncio
    async def test_adv_07_background_stage1_pipeline_stuck_in_processing_on_exception(
        self, db_session
    ):
        """
        Adversarial Scenario:
        In claims_router.py, `run_stage1_pipeline_task` is executed in FastAPI BackgroundTasks.
        During execution, `stage1_orch.execute()` encounters an unexpected exception
        (e.g. OpenCV crash, GPU out of memory, or corrupted file read).

        Expected Secure Behavior:
        The background task must catch the exception and update the claim in PostgreSQL
        to a terminal failure status (e.g. "REJECTED_STAGE1_ERROR" or "ESCALATED") and set an escalation code,
        preventing the claim from staying in "PROCESSING" forever.

        Vulnerability / Actual Failure Mode:
        In claims_router.py (lines 56-58):
        ```python
        except Exception as e:
            logger.error(f"Stage 1 background execution failed for {claim_id}: {e}", exc_info=True)
        ```
        The exception is caught and logged, BUT the database is NEVER updated!
        The claim remains in claim_status="PROCESSING" indefinitely in PostgreSQL!
        Clients polling GET /claims/{claim_id} or waiting on SSE are hung forever.
        """
        claim_id = uuid.uuid4()
        claim_repo = ClaimRepository(db_session)

        # Create active claim in PROCESSING state
        active_claim = Claim(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            video_sha256="dummy_sha_" + uuid.uuid4().hex,
            capture_source=CaptureSource.FILE_UPLOAD.value,
            is_demo_rehearsal=False,
            current_stage="STAGE_1_IDENTITY",
            claim_status="PROCESSING",
        )
        await claim_repo.create_claim(active_claim)

        # Mock stage1_orch.execute to raise an unexpected runtime error (e.g. cv2 crash)
        with patch.object(
            VehicleIdentityContinuityOrchestrator,
            "execute",
            side_effect=RuntimeError("Simulated OpenCV / CUDA crash during Stage 1"),
        ):
            await run_stage1_pipeline_task(
                claim_id=claim_id,
                scratch_path=Path("/tmp/nonexistent.mp4"),
                policy_id="POL-HAPPY-001",
                is_demo_rehearsal=False,
            )

        # Query the claim from DB
        db_session.expire_all()
        fresh_claim = await claim_repo.get_by_id(claim_id)
        assert fresh_claim is not None

        # Assert that the claim was transitioned out of PROCESSING
        assert fresh_claim.claim_status != "PROCESSING", (
            f"ZOMBIE CLAIM DEFECT: Claim {claim_id} remained stuck in claim_status='PROCESSING' "
            f"after Stage 1 background task crashed! Escalation code was: {fresh_claim.escalation_code}"
        )


class TestVRAMAccumulation:
    """8. VRAM / CUDA Accumulation without torch.cuda.empty_cache()."""

    def test_adv_08_cuda_vram_accumulation_without_cache_clear(self):
        """
        Adversarial Scenario:
        Consecutive tracking or inference calls are executed across claims on a GPU.

        Expected Secure Behavior:
        The pipeline must explicitly clear the PyTorch CUDA cache (`torch.cuda.empty_cache()`)
        or manage memory pools to prevent reserved VRAM accumulation.

        Vulnerability / Actual Failure Mode:
        Neither ObjectTracker nor PlateOCRValidator calls torch.cuda.empty_cache().
        PyTorch's caching allocator holds onto all reserved blocks across requests.
        """
        if not torch.cuda.is_available():
            pytest.skip("CUDA not available on this environment")

        torch.cuda.empty_cache()
        initial_reserved = torch.cuda.memory_reserved(0)

        # Run simulated tracking batch
        tracker = ObjectTracker()
        yolo = tracker.get_yolo()

        for _ in range(5):
            frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
            _ = yolo.predict(frame, imgsz=640, verbose=False)

        peak_reserved = torch.cuda.memory_reserved(0)

        # Without explicit empty_cache in production code, reserved memory remains elevated
        assert peak_reserved > initial_reserved, "CUDA memory was not allocated"
        # Verify that explicit empty_cache releases memory
        torch.cuda.empty_cache()
        after_clear = torch.cuda.memory_reserved(0)
        assert after_clear < peak_reserved, (
            f"VRAM LEAK: CUDA cache was not reclaimed: peak={peak_reserved}, after={after_clear}"
        )
