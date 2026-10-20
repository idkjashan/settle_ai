"""
tests/vehicle_identity_continuity/test_photo_pack_continuity.py
Unit and integration tests for Photo Pack Vehicle Identity Grounding in Stage 1.
Verifies ANPR plate OCR, body paint color HSV grounding, canonical keyframe mapping,
and Stage 2 handoff payload construction.
"""
import uuid
from pathlib import Path
import cv2
import numpy as np
import pytest

from app.domain.vehicle_identity_continuity.orchestrator import VehicleIdentityContinuityOrchestrator
from app.domain.vehicle_identity_continuity.schemas import (
    Stage2HandoffPayload,
    VehicleContinuityTelemetryDTO,
)
from app.infrastructure.db.models import Claim
from app.infrastructure.db.repositories import PolicyRepository, ClaimRepository
from tests.vehicle_identity_continuity.conftest import overlay_plate_on_car


def _save_jpeg(img: np.ndarray, path: Path) -> Path:
    cv2.imwrite(str(path), img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    return path


@pytest.mark.asyncio
class TestPhotoPackContinuity:
    """Test suite for photo pack processing in Stage 1."""

    async def test_photo_pack_continuity_happy_path(
        self, db_session, redis_mgr, base_white_image, tmp_path: Path
    ):
        """Happy path: Plate matches policy plate (MH 12 DE 1433), body color matches (WHITE),
        canonical keyframes are mapped, and claim transitions to STAGE_2_SEGMENTATION.
        """
        policy_repo = PolicyRepository(db_session)
        claim_repo = ClaimRepository(db_session)
        orchestrator = VehicleIdentityContinuityOrchestrator(
            policy_repo=policy_repo,
            claim_repo=claim_repo,
            redis_mgr=redis_mgr,
        )

        # 1. Prepare 3 photos (plate view, context view, damage closeup view)
        plate_img = overlay_plate_on_car(base_white_image, "MH 12 DE 1433")
        plate_path = _save_jpeg(plate_img, tmp_path / "front_bumper.jpg")

        context_img = base_white_image.copy()
        context_path = _save_jpeg(context_img, tmp_path / "side_body_panel.jpg")

        h, w = base_white_image.shape[:2]
        damage_crop = cv2.resize(base_white_image[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4], (w, h))
        damage_path = _save_jpeg(damage_crop, tmp_path / "damage_closeup_primary.jpg")

        photos = [plate_path, context_path, damage_path]

        # 2. Seed active claim in DB
        claim_id = uuid.uuid4()
        test_claim = Claim(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            video_sha256=f"sha256_photo_{uuid.uuid4().hex[:8]}",
            capture_source="FILE_UPLOAD",
            is_demo_rehearsal=True,
            current_stage="STAGE_1_IDENTITY",
            claim_status="PROCESSING",
        )
        await claim_repo.create_claim(test_claim)

        # 3. Execute Stage 1 for Photo Pack
        telemetry: VehicleContinuityTelemetryDTO = await orchestrator.execute_photo_pack(
            claim_id=claim_id,
            photo_paths=photos,
            policy_id="POL-HAPPY-001",
            is_demo_rehearsal=True,
        )

        # 4. Verify telemetry assertions
        assert telemetry.passed is True
        assert telemetry.escalation_code is None
        assert telemetry.cut_report.is_continuous is True
        assert telemetry.plate_report.is_verified is True
        assert telemetry.plate_report.expected_plate == "MH12DE1433"
        assert telemetry.color_report.is_color_match is True
        assert telemetry.color_report.expected_color_name == "WHITE"
        assert telemetry.tracking_report.is_persistent is True

        # 5. Verify canonical keyframe mapping
        saved_kf = telemetry.tracking_report.saved_keyframes
        assert "front_bumper" in saved_kf
        assert "side_body_panel" in saved_kf
        assert "damage_closeup_primary" in saved_kf
        assert saved_kf["front_bumper"] == str(plate_path)

        # 6. Verify state update in DB
        from tests.in_memory_db import in_memory_db
        persisted_claim = in_memory_db.claims[claim_id]
        assert persisted_claim.current_stage == "STAGE_2_SEGMENTATION"
        assert persisted_claim.claim_status == "PROCESSING"

    async def test_photo_pack_wrong_plate_fails(
        self, db_session, redis_mgr, base_white_image, tmp_path: Path
    ):
        """When photo pack carries a mismatched plate, Stage 1 rejects with S1_PLATE_MISMATCH / ESC-01."""
        policy_repo = PolicyRepository(db_session)
        claim_repo = ClaimRepository(db_session)
        orchestrator = VehicleIdentityContinuityOrchestrator(
            policy_repo=policy_repo,
            claim_repo=claim_repo,
            redis_mgr=redis_mgr,
        )

        # Plate with different registration number
        wrong_plate_img = overlay_plate_on_car(base_white_image, "DL 01 AB 9999")
        p1 = _save_jpeg(wrong_plate_img, tmp_path / "front_bumper.jpg")
        p2 = _save_jpeg(base_white_image, tmp_path / "side_body_panel.jpg")
        p3 = _save_jpeg(base_white_image, tmp_path / "damage_closeup_primary.jpg")

        claim_id = uuid.uuid4()
        test_claim = Claim(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            video_sha256=f"sha256_wrong_{uuid.uuid4().hex[:8]}",
            capture_source="FILE_UPLOAD",
            is_demo_rehearsal=True,
            current_stage="STAGE_1_IDENTITY",
            claim_status="PROCESSING",
        )
        await claim_repo.create_claim(test_claim)

        telemetry = await orchestrator.execute_photo_pack(
            claim_id=claim_id,
            photo_paths=[p1, p2, p3],
            policy_id="POL-HAPPY-001",
            is_demo_rehearsal=True,
        )

        assert telemetry.passed is False
        assert telemetry.escalation_code == "ESC-01"
        assert telemetry.plate_report.is_verified is False

        from tests.in_memory_db import in_memory_db
        persisted = in_memory_db.claims[claim_id]
        assert persisted.claim_status == "REJECTED_STAGE1_IDENTITY"
        assert persisted.escalation_code == "ESC-01"

    async def test_photo_pack_wrong_color_fails(
        self, db_session, redis_mgr, base_blue_image, tmp_path: Path
    ):
        """When vehicle in photos is blue but policy records WHITE, Stage 1 rejects with S1_COLOR_MISMATCH."""
        policy_repo = PolicyRepository(db_session)
        claim_repo = ClaimRepository(db_session)
        orchestrator = VehicleIdentityContinuityOrchestrator(
            policy_repo=policy_repo,
            claim_repo=claim_repo,
            redis_mgr=redis_mgr,
        )

        # Blue car with matching plate string
        blue_plate_img = overlay_plate_on_car(base_blue_image, "MH 12 DE 1433")
        p1 = _save_jpeg(blue_plate_img, tmp_path / "front_bumper.jpg")
        p2 = _save_jpeg(base_blue_image, tmp_path / "side_body_panel.jpg")
        p3 = _save_jpeg(base_blue_image, tmp_path / "damage_closeup_primary.jpg")

        claim_id = uuid.uuid4()
        test_claim = Claim(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",  # expects WHITE
            video_sha256=f"sha256_color_{uuid.uuid4().hex[:8]}",
            capture_source="FILE_UPLOAD",
            is_demo_rehearsal=True,
            current_stage="STAGE_1_IDENTITY",
            claim_status="PROCESSING",
        )
        await claim_repo.create_claim(test_claim)

        telemetry = await orchestrator.execute_photo_pack(
            claim_id=claim_id,
            photo_paths=[p1, p2, p3],
            policy_id="POL-HAPPY-001",
            is_demo_rehearsal=True,
        )

        assert telemetry.passed is False
        assert telemetry.escalation_code == "ESC-01"
        assert telemetry.plate_report.is_verified is True
        assert telemetry.color_report.is_color_match is False
        assert telemetry.color_report.failure_code == "S1_COLOR_MISMATCH"

        from tests.in_memory_db import in_memory_db
        persisted = in_memory_db.claims[claim_id]
        assert persisted.claim_status == "REJECTED_STAGE1_IDENTITY"
        assert "S1_COLOR_MISMATCH" in persisted.failure_codes

    async def test_photo_pack_stage2_handoff_payload_construction(
        self, db_session, redis_mgr, base_white_image, tmp_path: Path
    ):
        """Verifies that Stage2HandoffPayload is cleanly constructible from Photo Pack telemetry."""
        policy_repo = PolicyRepository(db_session)
        claim_repo = ClaimRepository(db_session)
        orchestrator = VehicleIdentityContinuityOrchestrator(
            policy_repo=policy_repo,
            claim_repo=claim_repo,
            redis_mgr=redis_mgr,
        )

        plate_img = overlay_plate_on_car(base_white_image, "MH 12 DE 1433")
        p1 = _save_jpeg(plate_img, tmp_path / "front_bumper.jpg")
        p2 = _save_jpeg(base_white_image, tmp_path / "side_body_panel.jpg")
        p3 = _save_jpeg(base_white_image, tmp_path / "damage_closeup_primary.jpg")

        claim_id = uuid.uuid4()
        test_claim = Claim(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            video_sha256=f"sha256_s2_{uuid.uuid4().hex[:8]}",
            capture_source="FILE_UPLOAD",
            is_demo_rehearsal=True,
            current_stage="STAGE_1_IDENTITY",
            claim_status="PROCESSING",
        )
        await claim_repo.create_claim(test_claim)

        telemetry = await orchestrator.execute_photo_pack(
            claim_id=claim_id,
            photo_paths=[p1, p2, p3],
            policy_id="POL-HAPPY-001",
            is_demo_rehearsal=True,
        )
        assert telemetry.passed is True

        handoff = Stage2HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            scratch_video_path=str(p1),
            keyframe_paths=telemetry.tracking_report.saved_keyframes,
            vehicle_telemetry=telemetry,
        )
        assert handoff.claim_id == claim_id
        assert len(handoff.keyframe_paths) >= 3
        assert "front_bumper" in handoff.keyframe_paths
        assert handoff.vehicle_telemetry.passed is True

    async def test_photo_pack_unnamed_photos_auto_classified(
        self, db_session, redis_mgr, base_white_image, tmp_path: Path
    ):
        """When photos have generic names (e.g. img_0.jpg, img_1.jpg), orchestrator scans
        and correctly discovers the plate photo and maps canonical keyframes.
        """
        policy_repo = PolicyRepository(db_session)
        claim_repo = ClaimRepository(db_session)
        orchestrator = VehicleIdentityContinuityOrchestrator(
            policy_repo=policy_repo,
            claim_repo=claim_repo,
            redis_mgr=redis_mgr,
        )

        # Plate photo is generically named 'img_0.jpg'
        plate_img = overlay_plate_on_car(base_white_image, "MH 12 DE 1433")
        p0 = _save_jpeg(plate_img, tmp_path / "img_0.jpg")
        p1 = _save_jpeg(base_white_image, tmp_path / "img_1.jpg")
        p2 = _save_jpeg(base_white_image, tmp_path / "img_2.jpg")

        claim_id = uuid.uuid4()
        test_claim = Claim(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            video_sha256=f"sha256_unnamed_{uuid.uuid4().hex[:8]}",
            capture_source="FILE_UPLOAD",
            is_demo_rehearsal=True,
            current_stage="STAGE_1_IDENTITY",
            claim_status="PROCESSING",
        )
        await claim_repo.create_claim(test_claim)

        telemetry = await orchestrator.execute_photo_pack(
            claim_id=claim_id,
            photo_paths=[p0, p1, p2],
            policy_id="POL-HAPPY-001",
            is_demo_rehearsal=True,
        )

        assert telemetry.passed is True
        assert telemetry.plate_report.is_verified is True
        assert telemetry.tracking_report.saved_keyframes["front_bumper"] == str(p0)
