import io
from pathlib import Path
from typing import List
import cv2
import numpy as np
import pytest
from httpx import AsyncClient

from app.domain.fast_fail_gate.schemas import (
    CaptureModality,
    CaptureSource,
    FastFailFailureCode,
)
from app.domain.fast_fail_gate.container_forensics import (
    container_forensics_validator,
    validate_photo_pack,
)
from app.domain.fast_fail_gate.visual_quality_gate import (
    visual_quality_validator,
    validate_photos,
)
from app.domain.fast_fail_gate.orchestrator import FastFailGateOrchestrator
from app.domain.fast_fail_gate.policy_dedupe_gate import PolicyAndDedupeGate
from app.domain.fast_fail_gate.remediation_mapper import remediation_mapper
from app.infrastructure.storage.scratch_ingest import scratch_ingest_service
from app.infrastructure.storage.s3_client import s3_client
from app.infrastructure.cache.redis_manager import redis_manager
from app.infrastructure.db.repositories import PolicyRepository, ClaimRepository
from tests.in_memory_db import FakeAsyncSession


def make_synthetic_photo(
    path: Path,
    width: int = 1920,
    height: int = 1080,
    pattern: str = "sharp",
    fmt: str = "JPEG",
) -> Path:
    """Creates synthetic still images for testing photo pack gates."""
    if pattern == "dark":
        img = np.full((height, width, 3), 20, dtype=np.uint8)
    elif pattern == "bright":
        img = np.full((height, width, 3), 250, dtype=np.uint8)
    elif pattern == "blurry":
        # Uniform color with no edges yields near-zero Laplacian variance (< 5.0)
        img = np.full((height, width, 3), 128, dtype=np.uint8)
    else:  # sharp
        img = np.full((height, width, 3), 128, dtype=np.uint8)
        # Add high-contrast geometric features and text to guarantee Laplacian var > 100
        for i in range(0, width, 60):
            cv2.line(img, (i, 0), (i, height), (255, 255, 255), 3)
            cv2.line(img, (i + 30, 0), (i + 30, height), (0, 0, 0), 3)
        cv2.putText(
            img, "TEST PHOTO VEHICLE PLATE", (100, height // 2),
            cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 255), 4
        )
        cv2.circle(img, (width // 2, height // 2), 150, (0, 255, 0), 6)

    if fmt == "PNG":
        cv2.imwrite(str(path), img)
    else:
        cv2.imwrite(str(path), img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    return path


class TestPhotoPackForensicsGates:
    """Unit tests for container and format forensics on photo packs."""

    def test_validate_photo_pack_valid_counts(self, tmp_path: Path):
        """Valid photo pack counts (3 to 6 photos) must pass container validation."""
        photos = [
            make_synthetic_photo(tmp_path / f"p_{i}.jpg", 1920, 1080, "sharp", "JPEG")
            for i in range(3)
        ]
        rep = validate_photo_pack(photos)
        assert rep.passed is True
        assert rep.photo_count == 3
        assert len(rep.failure_codes) == 0

        # Test upper boundary: 6 photos
        more_photos = [
            make_synthetic_photo(tmp_path / f"p6_{i}.jpg", 1920, 1080, "sharp", "JPEG")
            for i in range(6)
        ]
        rep6 = validate_photo_pack(more_photos)
        assert rep6.passed is True
        assert rep6.photo_count == 6

    def test_validate_photo_pack_reject_under_3_photos(self, tmp_path: Path):
        """Photo pack with fewer than 3 photos must fail with INVALID_PHOTO_COUNT."""
        photos = [
            make_synthetic_photo(tmp_path / f"under_{i}.jpg", 1920, 1080, "sharp", "JPEG")
            for i in range(2)
        ]
        rep = validate_photo_pack(photos)
        assert rep.passed is False
        assert FastFailFailureCode.INVALID_PHOTO_COUNT in rep.failure_codes

    def test_validate_photo_pack_reject_over_6_photos(self, tmp_path: Path):
        """Photo pack with more than 6 photos must fail with INVALID_PHOTO_COUNT."""
        photos = [
            make_synthetic_photo(tmp_path / f"over_{i}.jpg", 1920, 1080, "sharp", "JPEG")
            for i in range(7)
        ]
        rep = validate_photo_pack(photos)
        assert rep.passed is False
        assert FastFailFailureCode.INVALID_PHOTO_COUNT in rep.failure_codes

    def test_validate_photo_pack_supports_png_and_jpeg(self, tmp_path: Path):
        """JPEG and PNG formats must both be recognized and accepted."""
        p1 = make_synthetic_photo(tmp_path / "photo_1.jpg", 1920, 1080, "sharp", "JPEG")
        p2 = make_synthetic_photo(tmp_path / "photo_2.png", 1920, 1080, "sharp", "PNG")
        p3 = make_synthetic_photo(tmp_path / "photo_3.jpeg", 1920, 1080, "sharp", "JPEG")
        rep = validate_photo_pack([p1, p2, p3])
        assert rep.passed is True
        assert "JPEG" in rep.file_formats
        assert "PNG" in rep.file_formats

    def test_validate_photo_pack_rejects_unsupported_format(self, tmp_path: Path):
        """Corrupt or non-image files must fail with UNSUPPORTED_PHOTO_FORMAT."""
        p1 = make_synthetic_photo(tmp_path / "valid1.jpg", 1920, 1080, "sharp", "JPEG")
        p2 = make_synthetic_photo(tmp_path / "valid2.jpg", 1920, 1080, "sharp", "JPEG")
        bad = tmp_path / "bad.txt"
        bad.write_text("This is not an image file.")

        rep = validate_photo_pack([p1, p2, bad])
        assert rep.passed is False
        assert FastFailFailureCode.UNSUPPORTED_PHOTO_FORMAT in rep.failure_codes

    def test_validate_photo_pack_rejects_low_resolution(self, tmp_path: Path):
        """Photos below 1080p standard (min < 720 or max < 1080) must fail with RESOLUTION_TOO_LOW."""
        p1 = make_synthetic_photo(tmp_path / "p1.jpg", 1920, 1080, "sharp", "JPEG")
        p2 = make_synthetic_photo(tmp_path / "p2.jpg", 1920, 1080, "sharp", "JPEG")
        low_res = make_synthetic_photo(tmp_path / "lowres.jpg", 640, 480, "sharp", "JPEG")

        rep = validate_photo_pack([p1, p2, low_res])
        assert rep.passed is False
        assert FastFailFailureCode.RESOLUTION_TOO_LOW in rep.failure_codes


class TestPhotoPackVisualQualityGates:
    """Unit tests for visual quality gate on still photos (sharpness & luminance)."""

    def test_validate_photos_happy_path(self, tmp_path: Path):
        """Sharp photos with balanced lighting pass visual quality checks."""
        photos = [
            make_synthetic_photo(tmp_path / f"vq_{i}.jpg", 1920, 1080, "sharp", "JPEG")
            for i in range(3)
        ]
        rep = validate_photos(photos)
        assert rep.passed is True
        assert rep.mean_luminance_aggregate >= 45.0
        assert rep.mean_luminance_aggregate <= 235.0
        assert rep.mean_sharpness_aggregate >= 60.0

    def test_validate_photos_dark_photo_rejected(self, tmp_path: Path):
        """Under-exposed photo (mean luminance < 45.0) triggers PHOTO_TOO_DARK."""
        p1 = make_synthetic_photo(tmp_path / "ok1.jpg", 1920, 1080, "sharp", "JPEG")
        p2 = make_synthetic_photo(tmp_path / "ok2.jpg", 1920, 1080, "sharp", "JPEG")
        dark = make_synthetic_photo(tmp_path / "dark.jpg", 1920, 1080, "dark", "JPEG")

        rep = validate_photos([p1, p2, dark])
        assert rep.passed is False
        assert FastFailFailureCode.PHOTO_TOO_DARK in rep.failure_codes
        assert rep.dark_photo_count >= 1

    def test_validate_photos_bright_photo_rejected(self, tmp_path: Path):
        """Overexposed photo (mean luminance > 235.0) triggers PHOTO_TOO_BRIGHT."""
        p1 = make_synthetic_photo(tmp_path / "ok1.jpg", 1920, 1080, "sharp", "JPEG")
        p2 = make_synthetic_photo(tmp_path / "ok2.jpg", 1920, 1080, "sharp", "JPEG")
        bright = make_synthetic_photo(tmp_path / "bright.jpg", 1920, 1080, "bright", "JPEG")

        rep = validate_photos([p1, p2, bright])
        assert rep.passed is False
        assert FastFailFailureCode.PHOTO_TOO_BRIGHT in rep.failure_codes
        assert rep.bright_photo_count >= 1

    def test_validate_photos_blurry_photo_rejected(self, tmp_path: Path):
        """Motion-blurred photo (Laplacian variance < 60.0) triggers PHOTO_TOO_BLURRY."""
        p1 = make_synthetic_photo(tmp_path / "ok1.jpg", 1920, 1080, "sharp", "JPEG")
        p2 = make_synthetic_photo(tmp_path / "ok2.jpg", 1920, 1080, "sharp", "JPEG")
        blurry = make_synthetic_photo(tmp_path / "blurry.jpg", 1920, 1080, "blurry", "JPEG")

        rep = validate_photos([p1, p2, blurry])
        assert rep.passed is False
        assert FastFailFailureCode.PHOTO_TOO_BLURRY in rep.failure_codes
        assert rep.blurry_photo_count >= 1


@pytest.mark.asyncio
class TestPhotoPackOrchestratorAndApi:
    """End-to-end unit tests for FastFailGateOrchestrator and API endpoint with photo packs."""

    async def test_orchestrator_execute_photo_pack_happy_path(self, tmp_path: Path):
        """execute_photo_pack with valid policy and valid photos returns passed=True."""
        db = FakeAsyncSession()
        policy_repo = PolicyRepository(db)
        claim_repo = ClaimRepository(db)
        tier1_gate = PolicyAndDedupeGate(policy_repo, claim_repo)

        orchestrator = FastFailGateOrchestrator(
            ingest_service=scratch_ingest_service,
            redis_mgr=redis_manager,
            tier1_gate=tier1_gate,
            container_validator=container_forensics_validator,
            visual_validator=visual_quality_validator,
            remediation_mapper=remediation_mapper,
            claim_repo=claim_repo,
            s3_client=s3_client,
        )

        photos = [
            make_synthetic_photo(tmp_path / f"valid_{i}.jpg", 1920, 1080, "sharp", "JPEG")
            for i in range(3)
        ]

        res = await orchestrator.execute_photo_pack(
            policy_id="POL-HAPPY-001",
            photo_paths=photos,
            is_demo_rehearsal=True,
        )
        assert res.passed is True
        assert res.claim_id is not None
        assert res.telemetry is not None
        assert res.telemetry.capture_modality == CaptureModality.PHOTO_PACK
        assert res.telemetry.photo_metadata_report is not None
        assert res.telemetry.photo_metadata_report.passed is True
        assert res.telemetry.photo_visual_report is not None
        assert res.telemetry.photo_visual_report.passed is True

    async def test_api_upload_photo_pack_endpoint_accepted(self, async_client: AsyncClient, tmp_path: Path):
        """POST /api/v1/claims/upload with photo_files returns HTTP 202 Accepted."""
        p1 = make_synthetic_photo(tmp_path / "plate.jpg", 1920, 1080, "sharp", "JPEG")
        p2 = make_synthetic_photo(tmp_path / "context.jpg", 1920, 1080, "sharp", "JPEG")
        p3 = make_synthetic_photo(tmp_path / "closeup.jpg", 1920, 1080, "sharp", "JPEG")

        files = [
            ("photo_files", ("plate.jpg", p1.read_bytes(), "image/jpeg")),
            ("photo_files", ("context.jpg", p2.read_bytes(), "image/jpeg")),
            ("photo_files", ("closeup.jpg", p3.read_bytes(), "image/jpeg")),
        ]
        data = {
            "policy_id": "POL-HAPPY-001",
            "capture_source": "FILE_UPLOAD",
            "is_demo_rehearsal": "true",
        }

        response = await async_client.post("/api/v1/claims/upload", data=data, files=files)
        assert response.status_code == 202
        body = response.json()
        assert body["passed"] is True
        assert body["claim_id"] is not None
        assert body["telemetry"]["capture_modality"] == "PHOTO_PACK"

    async def test_api_upload_photo_pack_under_count_rejected(self, async_client: AsyncClient, tmp_path: Path):
        """POST /api/v1/claims/upload with 2 photos returns HTTP 200 with INVALID_PHOTO_COUNT."""
        p1 = make_synthetic_photo(tmp_path / "p1.jpg", 1920, 1080, "sharp", "JPEG")
        p2 = make_synthetic_photo(tmp_path / "p2.jpg", 1920, 1080, "sharp", "JPEG")

        files = [
            ("photo_files", ("p1.jpg", p1.read_bytes(), "image/jpeg")),
            ("photo_files", ("p2.jpg", p2.read_bytes(), "image/jpeg")),
        ]
        data = {
            "policy_id": "POL-HAPPY-001",
            "capture_source": "FILE_UPLOAD",
            "is_demo_rehearsal": "true",
        }

        response = await async_client.post("/api/v1/claims/upload", data=data, files=files)
        assert response.status_code == 200
        body = response.json()
        assert body["passed"] is False
        assert body["escalation_code"] == "ESC-00"
        assert FastFailFailureCode.INVALID_PHOTO_COUNT.value in body["failure_codes"]
        assert body["remediation"]["can_retry"] is True
