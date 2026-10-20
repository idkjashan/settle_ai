from pathlib import Path
import pytest
from httpx import AsyncClient

from app.domain.fast_fail_gate.schemas import FastFailFailureCode
from app.domain.fast_fail_gate.container_forensics import container_forensics_validator


@pytest.mark.asyncio
class TestFastFailGate:
    """
    Stage 0 (Fast-Fail Gate) Verification Suite
    Implements tests specified in LLD Section 10: T0-01 through T0-21.
    """

    async def test_t0_01_happy_path_valid_video_accepted(
        self, async_client: AsyncClient, clean_720p_video: Path
    ):
        """T0-01: Happy path valid 720p 15s video with POL-HAPPY-001 -> HTTP 202 Accepted."""
        with open(clean_720p_video, "rb") as f:
            files = {"video_file": ("walkaround.mp4", f.read(), "video/mp4")}
            data = {
                "policy_id": "POL-HAPPY-001",
                "capture_source": "FILE_UPLOAD",
                "is_demo_rehearsal": "false",
            }
            response = await async_client.post("/api/v1/claims/upload", data=data, files=files)

        assert response.status_code == 202
        res = response.json()
        assert res["passed"] is True
        assert res["escalation_code"] is None
        assert len(res["failure_codes"]) == 0
        claim_id = res["claim_id"]
        assert claim_id is not None
        assert res["sse_stream_url"] == f"/api/v1/claims/{claim_id}/events"

        # Telemetry verification
        telemetry = res["telemetry"]
        assert telemetry is not None
        assert telemetry["tier1_report"]["passed"] is True
        assert telemetry["container_report"]["passed"] is True
        assert telemetry["visual_report"]["passed"] is True
        assert telemetry["container_report"]["width"] >= 720
        assert telemetry["container_report"]["duration_sec"] >= 5.0
        assert telemetry["visual_report"]["mean_luminance_aggregate"] >= 45.0
        assert telemetry["visual_report"]["mean_sharpness_aggregate"] >= 80.0

    async def test_t0_05_unknown_policy_rejected(
        self, async_client: AsyncClient, clean_720p_video: Path
    ):
        """T0-05: Non-existent policy -> REJECT POLICY_NOT_FOUND (HTTP 200, ESC-00)."""
        with open(clean_720p_video, "rb") as f:
            files = {"video_file": ("walkaround.mp4", f.read(), "video/mp4")}
            data = {
                "policy_id": "POL-NON-EXISTENT-999",
                "capture_source": "FILE_UPLOAD",
                "is_demo_rehearsal": "false",
            }
            response = await async_client.post("/api/v1/claims/upload", data=data, files=files)

        assert response.status_code == 200
        res = response.json()
        assert res["passed"] is False
        assert res["escalation_code"] == "ESC-00"
        assert FastFailFailureCode.POLICY_NOT_FOUND.value in res["failure_codes"]
        assert res["remediation"]["can_retry"] is False

    async def test_t0_06_expired_policy_rejected(
        self, async_client: AsyncClient, clean_720p_video: Path
    ):
        """T0-06: Expired policy (POL-EXPIRED-002) -> REJECT POLICY_EXPIRED_OR_NOT_STARTED."""
        with open(clean_720p_video, "rb") as f:
            files = {"video_file": ("walkaround.mp4", f.read(), "video/mp4")}
            data = {
                "policy_id": "POL-EXPIRED-002",
                "capture_source": "FILE_UPLOAD",
                "is_demo_rehearsal": "false",
            }
            response = await async_client.post("/api/v1/claims/upload", data=data, files=files)

        assert response.status_code == 200
        res = response.json()
        assert res["passed"] is False
        assert res["escalation_code"] == "ESC-00"
        assert FastFailFailureCode.POLICY_EXPIRED_OR_NOT_STARTED.value in res["failure_codes"]
        assert res["remediation"]["can_retry"] is False

    async def test_t0_08_annual_claim_limit_reached_rejected(
        self, async_client: AsyncClient, clean_720p_video: Path
    ):
        """T0-08: Policy with maxed claims (POL-CLAIMCAP-004) -> REJECT ANNUAL_CASH_CLAIM_LIMIT_REACHED."""
        with open(clean_720p_video, "rb") as f:
            files = {"video_file": ("walkaround.mp4", f.read(), "video/mp4")}
            data = {
                "policy_id": "POL-CLAIMCAP-004",
                "capture_source": "FILE_UPLOAD",
                "is_demo_rehearsal": "false",
            }
            response = await async_client.post("/api/v1/claims/upload", data=data, files=files)

        assert response.status_code == 200
        res = response.json()
        assert res["passed"] is False
        assert res["escalation_code"] == "ESC-00"
        assert FastFailFailureCode.ANNUAL_CASH_CLAIM_LIMIT_REACHED.value in res["failure_codes"]
        assert res["remediation"]["can_retry"] is False

    async def test_t0_09_duplicate_video_submission_rejected(
        self, async_client: AsyncClient, clean_720p_video: Path
    ):
        """T0-09: Duplicate submission of identical video -> REJECT DUPLICATE_VIDEO_SUBMISSION."""
        video_bytes = clean_720p_video.read_bytes()

        # 1st upload succeeds
        files1 = {"video_file": ("walkaround.mp4", video_bytes, "video/mp4")}
        data1 = {
            "policy_id": "POL-HAPPY-001",
            "capture_source": "FILE_UPLOAD",
            "is_demo_rehearsal": "false",
        }
        res1 = await async_client.post("/api/v1/claims/upload", data=data1, files=files1)
        assert res1.status_code == 202
        assert res1.json()["passed"] is True

        # 2nd upload of identical file bytes -> blocked as duplicate
        files2 = {"video_file": ("walkaround.mp4", video_bytes, "video/mp4")}
        data2 = {
            "policy_id": "POL-HAPPY-001",
            "capture_source": "FILE_UPLOAD",
            "is_demo_rehearsal": "false",
        }
        res2 = await async_client.post("/api/v1/claims/upload", data=data2, files=files2)
        assert res2.status_code == 200
        data = res2.json()
        assert data["passed"] is False
        assert data["escalation_code"] == "ESC-00"
        assert FastFailFailureCode.DUPLICATE_VIDEO_SUBMISSION.value in data["failure_codes"]
        assert data["remediation"]["can_retry"] is True

    async def test_t0_11_demo_rehearsal_bypass_duplicate_check(
        self, async_client: AsyncClient, clean_720p_video: Path
    ):
        """T0-11: Demo rehearsal (is_demo_rehearsal=True) bypasses historical duplicate blocking."""
        video_bytes = clean_720p_video.read_bytes()

        # Upload 1 in demo rehearsal mode
        files1 = {"video_file": ("walkaround.mp4", video_bytes, "video/mp4")}
        data1 = {
            "policy_id": "POL-HAPPY-001",
            "capture_source": "FILE_UPLOAD",
            "is_demo_rehearsal": "true",
        }
        res1 = await async_client.post("/api/v1/claims/upload", data=data1, files=files1)
        assert res1.status_code == 202
        assert res1.json()["passed"] is True

        # Upload 2 with same video and is_demo_rehearsal=true -> also succeeds!
        files2 = {"video_file": ("walkaround.mp4", video_bytes, "video/mp4")}
        data2 = {
            "policy_id": "POL-HAPPY-001",
            "capture_source": "FILE_UPLOAD",
            "is_demo_rehearsal": "true",
        }
        res2 = await async_client.post("/api/v1/claims/upload", data=data2, files=files2)
        assert res2.status_code == 202
        assert res2.json()["passed"] is True

    async def test_t0_13_capcut_metadata_rejected(
        self, async_client: AsyncClient, capcut_video: Path
    ):
        """T0-13: Video with CapCut metadata tag -> REJECT METADATA_EDITED_VIDEO."""
        with open(capcut_video, "rb") as f:
            files = {"video_file": ("walkaround.mp4", f.read(), "video/mp4")}
            data = {
                "policy_id": "POL-HAPPY-001",
                "capture_source": "FILE_UPLOAD",
                "is_demo_rehearsal": "true",
            }
            response = await async_client.post("/api/v1/claims/upload", data=data, files=files)

        assert response.status_code == 200
        res = response.json()
        assert res["passed"] is False
        assert res["escalation_code"] == "ESC-00"
        assert FastFailFailureCode.METADATA_EDITED_VIDEO.value in res["failure_codes"]
        detected = res["telemetry"]["container_report"]["detected_editor_tag"]
        assert detected is not None
        assert "capcut" in detected.lower()
        assert res["remediation"]["can_retry"] is True

    async def test_t0_14_standard_lavf_libx264_whitelist_no_false_positive(
        self, clean_720p_video: Path
    ):
        """T0-14: Standard libx264 / Lavf encoders are explicitly whitelisted and do not trigger editor rejection."""
        file_size = clean_720p_video.stat().st_size
        report = container_forensics_validator.validate(
            video_path=clean_720p_video,
            sha256="test-sha",
            file_size_bytes=file_size,
        )
        assert FastFailFailureCode.METADATA_EDITED_VIDEO not in report.failure_codes
        assert report.detected_editor_tag is None

    async def test_t0_15_resolution_too_low_rejected(
        self, async_client: AsyncClient, lowres_video: Path
    ):
        """T0-15: Video resolution < 720p (640x360) -> REJECT RESOLUTION_TOO_LOW."""
        with open(lowres_video, "rb") as f:
            files = {"video_file": ("walkaround.mp4", f.read(), "video/mp4")}
            data = {
                "policy_id": "POL-HAPPY-001",
                "capture_source": "FILE_UPLOAD",
                "is_demo_rehearsal": "true",
            }
            response = await async_client.post("/api/v1/claims/upload", data=data, files=files)

        assert response.status_code == 200
        res = response.json()
        assert res["passed"] is False
        assert res["escalation_code"] == "ESC-00"
        assert FastFailFailureCode.RESOLUTION_TOO_LOW.value in res["failure_codes"]
        assert res["telemetry"]["container_report"]["width"] == 640
        assert res["telemetry"]["container_report"]["height"] == 360

    async def test_t0_16_duration_too_short_rejected(
        self, async_client: AsyncClient, short_video: Path
    ):
        """T0-16: Video duration < 5s (3s) -> REJECT DURATION_TOO_SHORT."""
        with open(short_video, "rb") as f:
            files = {"video_file": ("walkaround.mp4", f.read(), "video/mp4")}
            data = {
                "policy_id": "POL-HAPPY-001",
                "capture_source": "FILE_UPLOAD",
                "is_demo_rehearsal": "true",
            }
            response = await async_client.post("/api/v1/claims/upload", data=data, files=files)

        assert response.status_code == 200
        res = response.json()
        assert res["passed"] is False
        assert res["escalation_code"] == "ESC-00"
        assert FastFailFailureCode.DURATION_TOO_SHORT.value in res["failure_codes"]

    async def test_t0_17_duration_too_long_rejected(
        self, async_client: AsyncClient, long_video: Path
    ):
        """T0-17: Video duration > 60s (65s) -> REJECT DURATION_TOO_LONG."""
        with open(long_video, "rb") as f:
            files = {"video_file": ("walkaround.mp4", f.read(), "video/mp4")}
            data = {
                "policy_id": "POL-HAPPY-001",
                "capture_source": "FILE_UPLOAD",
                "is_demo_rehearsal": "true",
            }
            response = await async_client.post("/api/v1/claims/upload", data=data, files=files)

        assert response.status_code == 200
        res = response.json()
        assert res["passed"] is False
        assert res["escalation_code"] == "ESC-00"
        assert FastFailFailureCode.DURATION_TOO_LONG.value in res["failure_codes"]

    async def test_t0_18_dark_video_rejected(
        self, async_client: AsyncClient, dark_video: Path
    ):
        """T0-18: Dark video (mean Y < 45.0) -> REJECT VIDEO_TOO_DARK."""
        with open(dark_video, "rb") as f:
            files = {"video_file": ("walkaround.mp4", f.read(), "video/mp4")}
            data = {
                "policy_id": "POL-HAPPY-001",
                "capture_source": "FILE_UPLOAD",
                "is_demo_rehearsal": "true",
            }
            response = await async_client.post("/api/v1/claims/upload", data=data, files=files)

        assert response.status_code == 200
        res = response.json()
        assert res["passed"] is False
        assert res["escalation_code"] == "ESC-00"
        assert FastFailFailureCode.VIDEO_TOO_DARK.value in res["failure_codes"]
        assert res["telemetry"]["visual_report"]["mean_luminance_aggregate"] < 45.0

    async def test_t0_20_blurry_video_rejected(
        self, async_client: AsyncClient, blurry_video: Path
    ):
        """T0-20: Blurry video (Laplacian variance < 80.0) -> REJECT VIDEO_TOO_BLURRY."""
        with open(blurry_video, "rb") as f:
            files = {"video_file": ("walkaround.mp4", f.read(), "video/mp4")}
            data = {
                "policy_id": "POL-HAPPY-001",
                "capture_source": "FILE_UPLOAD",
                "is_demo_rehearsal": "true",
            }
            response = await async_client.post("/api/v1/claims/upload", data=data, files=files)

        assert response.status_code == 200
        res = response.json()
        assert res["passed"] is False
        assert res["escalation_code"] == "ESC-00"
        assert FastFailFailureCode.VIDEO_TOO_BLURRY.value in res["failure_codes"]
        assert res["telemetry"]["visual_report"]["mean_sharpness_aggregate"] < 80.0

    async def test_t0_21_corrupt_file_rejected(
        self, async_client: AsyncClient, corrupt_video: Path
    ):
        """T0-21: Corrupt container stream -> REJECT CONTAINER_PARSE_FAILED."""
        with open(corrupt_video, "rb") as f:
            files = {"video_file": ("walkaround.mp4", f.read(), "video/mp4")}
            data = {
                "policy_id": "POL-HAPPY-001",
                "capture_source": "FILE_UPLOAD",
                "is_demo_rehearsal": "true",
            }
            response = await async_client.post("/api/v1/claims/upload", data=data, files=files)

        assert response.status_code == 200
        res = response.json()
        assert res["passed"] is False
        assert res["escalation_code"] == "ESC-00"
        assert FastFailFailureCode.CONTAINER_PARSE_FAILED.value in res["failure_codes"]

    async def test_cancelled_policy_rejected(
        self, async_client: AsyncClient, clean_720p_video: Path
    ):
        """Test cancelled policy (POL-CANCELLED-005) -> REJECT POLICY_INACTIVE."""
        with open(clean_720p_video, "rb") as f:
            files = {"video_file": ("walkaround.mp4", f.read(), "video/mp4")}
            data = {
                "policy_id": "POL-CANCELLED-005",
                "capture_source": "FILE_UPLOAD",
                "is_demo_rehearsal": "true",
            }
            response = await async_client.post("/api/v1/claims/upload", data=data, files=files)

        assert response.status_code == 200
        res = response.json()
        assert res["passed"] is False
        assert FastFailFailureCode.POLICY_INACTIVE.value in res["failure_codes"]
