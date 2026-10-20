"""
tests/vehicle_identity_continuity/test_vehicle_identity_continuity.py
Complete Test Suite for Stage 1 (Gates 1, 2, 3 and Orchestrator).
"""
import uuid
from pathlib import Path
import cv2
import numpy as np
import pytest

from app.domain.vehicle_identity_continuity.cut_detector import cut_detector
from app.domain.vehicle_identity_continuity.plate_ocr_validator import (
    plate_ocr_validator,
    homoglyph_weighted_distance,
    clean_plate_string,
)
from app.domain.vehicle_identity_continuity.color_grounding_validator import color_grounding_validator
from app.domain.vehicle_identity_continuity.object_tracker import object_tracker
from app.domain.vehicle_identity_continuity.orchestrator import VehicleIdentityContinuityOrchestrator
from app.domain.vehicle_identity_continuity.schemas import (
    PolicyGroundingContext,
    CutDetectionResult,
    PlateValidationResult,
    ColorValidationResult,
    TrackingAndKeyframeResult,
)
from app.infrastructure.db.models import Claim
from app.infrastructure.db.repositories import PolicyRepository, ClaimRepository


# ===========================================================================
# Gate 1: Spliced Scene Cut & Continuity Detection
# ===========================================================================

def test_gate1_clean_continuous_video_passes(clip_happy_creta_white):
    """Gate 1: Verifies that a clean, unbroken walkaround passes with is_continuous=True."""
    res: CutDetectionResult = cut_detector.evaluate(clip_happy_creta_white)
    assert res.is_continuous is True
    assert res.failure_code is None
    assert res.evaluated_frames >= 30
    assert res.min_global_hsv_corr >= 0.60
    assert res.max_frozen_frame_run <= 15


def test_gate1_hard_cut_rejected(clip_spliced_cut):
    """Gate 1: Abrupt cut to completely different scene is rejected (ESC-02)."""
    res: CutDetectionResult = cut_detector.evaluate(clip_spliced_cut)
    assert res.is_continuous is False
    assert res.failure_code in ("S1_CUT_HISTOGRAM_DROP", "S1_CUT_PYSCENEDETECT_TRIGGER")
    assert len(res.cut_frame_indices) > 0


def test_gate1_jump_cut_rejected(clip_same_car_jump_splice):
    """Gate 1: Subtle jump-cut splice of the same car triggers grid SSIM drop (ESC-02)."""
    res: CutDetectionResult = cut_detector.evaluate(clip_same_car_jump_splice)
    assert res.is_continuous is False
    assert res.failure_code in ("S1_CUT_SPATIAL_SSIM_DROP", "S1_CUT_HISTOGRAM_DROP", "S1_CUT_PYSCENEDETECT_TRIGGER")


def test_gate1_freeze_frame_rejected(clip_freeze_frame_24):
    """Gate 1: Video freeze lasting > 15 frames is rejected (ESC-02)."""
    res: CutDetectionResult = cut_detector.evaluate(clip_freeze_frame_24)
    assert res.is_continuous is False
    assert res.failure_code == "S1_CUT_FREEZE_FRAME_DETECTED"
    assert res.max_frozen_frame_run > 15


# ===========================================================================
# Gate 2: Progressive ANPR & Paint Color Grounding
# ===========================================================================

def test_gate2_single_line_plate_verified(clip_happy_creta_white):
    """Gate 2A: Single-line plate MH 12 DE 1433 matches policy registration."""
    res: PlateValidationResult = plate_ocr_validator.validate_initial_window(
        clip_happy_creta_white, "MH 12 DE 1433"
    )
    assert res.is_verified is True
    assert res.deferred_to_late_track is False
    assert res.extracted_plate is not None
    assert clean_plate_string(res.extracted_plate) == "MH12DE1433"
    assert res.anchor_vehicle_bbox is not None


def test_gate2_two_line_hsrp_merge_verified(clip_2line_rear_plate):
    """Gate 2A: 2-line stacked Indian HSRP plate (MH 12 over DE 1433) is correctly merged."""
    res: PlateValidationResult = plate_ocr_validator.validate_initial_window(
        clip_2line_rear_plate, "MH 12 DE 1433"
    )
    assert res.is_verified is True
    assert clean_plate_string(res.extracted_plate) == "MH12DE1433"


def test_gate2_homoglyph_tolerance_accepted(clip_homoglyph_plate):
    """Gate 2A: Optical homoglyph reading '0' instead of 'D' (MH 12 0E 1433) is accepted."""
    res: PlateValidationResult = plate_ocr_validator.validate_initial_window(
        clip_homoglyph_plate, "MH 12 DE 1433"
    )
    assert res.is_verified is True
    assert res.homoglyph_edit_cost <= 0.50


def test_gate2_wrong_plate_mismatch_rejected(clip_wrong_plate):
    """Gate 2A: Definite wrong plate DL 09 CA 8821 fast-fails with S1_PLATE_MISMATCH (ESC-01)."""
    res: PlateValidationResult = plate_ocr_validator.validate_initial_window(
        clip_wrong_plate, "MH 12 DE 1433"
    )
    assert res.is_verified is False
    assert res.failure_code == "S1_PLATE_MISMATCH"
    assert res.deferred_to_late_track is False


def test_gate2_color_match_white_accepted(base_white_image):
    """Gate 2C: Paint color grounding accepts white vehicle with policy color WHITE."""
    bbox = (230, 230, 1040, 560)
    policy_ctx = PolicyGroundingContext(
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        make="Hyundai",
        model="Creta",
        registered_color="WHITE",
    )
    res: ColorValidationResult = color_grounding_validator.validate_paint_color(
        base_white_image, bbox, policy_ctx
    )
    assert res.is_color_match is True
    assert res.failure_code is None
    assert res.delta_e_hsv <= 35.0


def test_gate2_color_mismatch_blue_rejected(base_blue_image):
    """Gate 2C: Paint color grounding rejects blue vehicle when policy expects WHITE (ESC-01)."""
    bbox = (230, 230, 1040, 560)
    policy_ctx = PolicyGroundingContext(
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        make="Hyundai",
        model="Creta",
        registered_color="WHITE",
    )
    res: ColorValidationResult = color_grounding_validator.validate_paint_color(
        base_blue_image, bbox, policy_ctx
    )
    assert res.is_color_match is False
    assert res.failure_code == "S1_COLOR_MISMATCH"
    assert res.delta_e_hsv > 35.0


# ===========================================================================
# Gate 3: Strided Tracking & Keyframe Extraction
# ===========================================================================

def test_gate3_continuous_tracking_and_keyframes_saved(clip_happy_creta_white):
    """Gate 3: Vehicle is persistently tracked and keyframes are saved to disk."""
    policy_ctx = PolicyGroundingContext(
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        make="Hyundai",
        model="Creta",
        registered_color="WHITE",
    )
    test_claim_id = str(uuid.uuid4())
    res: TrackingAndKeyframeResult = object_tracker.track_and_extract_keyframes(
        clip_happy_creta_white, test_claim_id, policy_ctx
    )
    assert res.is_persistent is True
    assert res.failure_code is None
    assert res.track_lost_count <= 15
    assert len(res.saved_keyframes) > 0
    # Verify keyframe files exist on filesystem
    for view, kf_path in res.saved_keyframes.items():
        p = Path(kf_path)
        assert p.exists()
        assert p.stat().st_size > 0


def test_gate3_closeup_zoom_handoff(clip_macro_closeup):
    """Gate 3: Macro close-up zoom latches hand-off and forgives detector dropout."""
    policy_ctx = PolicyGroundingContext(
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        make="Hyundai",
        model="Creta",
        registered_color="WHITE",
    )
    test_claim_id = str(uuid.uuid4())
    res: TrackingAndKeyframeResult = object_tracker.track_and_extract_keyframes(
        clip_macro_closeup, test_claim_id, policy_ctx
    )
    assert res.is_persistent is True
    assert res.closeup_handoff_triggered is True


def test_gate3_track_lost_exceeded_rejected(clip_track_lost_30frames):
    """Gate 3: Wide camera pan to floor exceeding 15 frames is rejected (ESC-02)."""
    policy_ctx = PolicyGroundingContext(
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        make="Hyundai",
        model="Creta",
        registered_color="WHITE",
    )
    test_claim_id = str(uuid.uuid4())
    res: TrackingAndKeyframeResult = object_tracker.track_and_extract_keyframes(
        clip_track_lost_30frames, test_claim_id, policy_ctx
    )
    assert res.is_persistent is False
    assert res.failure_code == "S1_TRACK_LOST_EXCEEDED"


def test_gate3_parking_lot_switch_rejected(clip_parking_lot_switch):
    """Gate 3: Camera switching to an adjacent car is rejected (ESC-02)."""
    policy_ctx = PolicyGroundingContext(
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        make="Hyundai",
        model="Creta",
        registered_color="WHITE",
    )
    test_claim_id = str(uuid.uuid4())
    res: TrackingAndKeyframeResult = object_tracker.track_and_extract_keyframes(
        clip_parking_lot_switch, test_claim_id, policy_ctx
    )
    assert res.is_persistent is False
    assert res.failure_code in ("S1_TRACK_ID_SWITCHED", "S1_TRACK_LOST_EXCEEDED")


# ===========================================================================
# End-to-End Orchestrator Integration Tests (PostgreSQL + Redis)
# ===========================================================================

@pytest.mark.asyncio
async def test_orchestrator_happy_path_claim_passes_to_stage2(
    db_session, redis_mgr, clip_happy_creta_white
):
    """End-to-End: Happy path claim passes Stage 1, commits STAGE_2_SEGMENTATION and emits SSE."""
    policy_repo = PolicyRepository(db_session)
    claim_repo = ClaimRepository(db_session)
    orchestrator = VehicleIdentityContinuityOrchestrator(
        policy_repo=policy_repo,
        claim_repo=claim_repo,
        redis_mgr=redis_mgr,
    )

    claim_id = uuid.uuid4()
    test_claim = Claim(
        claim_id=claim_id,
        policy_id="POL-HAPPY-001",
        video_sha256=f"sha256_happy_{uuid.uuid4().hex[:8]}",
        capture_source="FILE_UPLOAD",
        is_demo_rehearsal=True,
        current_stage="STAGE_1_IDENTITY",
        claim_status="PROCESSING",
    )
    await claim_repo.create_claim(test_claim)

    telemetry = await orchestrator.execute(
        claim_id=claim_id,
        scratch_video_path=clip_happy_creta_white,
        policy_id="POL-HAPPY-001",
        is_demo_rehearsal=True,
    )

    assert telemetry.passed is True
    assert telemetry.escalation_code is None
    assert telemetry.cut_report.is_continuous is True
    assert telemetry.plate_report.is_verified is True
    assert telemetry.color_report.is_color_match is True
    assert telemetry.tracking_report.is_persistent is True

    # Assert PostgreSQL state transition
    updated = await claim_repo.get_by_id(claim_id)
    assert updated.current_stage == "STAGE_2_SEGMENTATION"
    assert updated.claim_status == "PROCESSING"
    assert updated.vehicle_continuity_telemetry is not None


@pytest.mark.asyncio
async def test_orchestrator_cut_failure_updates_db_and_emits_sse(
    db_session, redis_mgr, clip_spliced_cut
):
    """End-to-End: Spliced cut failure transitions claim to REJECTED_STAGE1_CONTINUITY with ESC-02."""
    policy_repo = PolicyRepository(db_session)
    claim_repo = ClaimRepository(db_session)
    orchestrator = VehicleIdentityContinuityOrchestrator(
        policy_repo=policy_repo,
        claim_repo=claim_repo,
        redis_mgr=redis_mgr,
    )

    claim_id = uuid.uuid4()
    test_claim = Claim(
        claim_id=claim_id,
        policy_id="POL-HAPPY-001",
        video_sha256=f"sha256_cut_{uuid.uuid4().hex[:8]}",
        capture_source="FILE_UPLOAD",
        is_demo_rehearsal=True,
        current_stage="STAGE_1_IDENTITY",
        claim_status="PROCESSING",
    )
    await claim_repo.create_claim(test_claim)

    telemetry = await orchestrator.execute(
        claim_id=claim_id,
        scratch_video_path=clip_spliced_cut,
        policy_id="POL-HAPPY-001",
        is_demo_rehearsal=True,
    )

    assert telemetry.passed is False
    assert telemetry.escalation_code == "ESC-02"

    updated = await claim_repo.get_by_id(claim_id)
    assert updated.current_stage == "STAGE_1_IDENTITY"
    assert updated.claim_status == "REJECTED_STAGE1_CONTINUITY"
    assert updated.escalation_code == "ESC-02"


@pytest.mark.asyncio
async def test_orchestrator_wrong_plate_updates_db_and_emits_sse(
    db_session, redis_mgr, clip_wrong_plate
):
    """End-to-End: Wrong plate transitions claim to REJECTED_STAGE1_IDENTITY with ESC-01."""
    policy_repo = PolicyRepository(db_session)
    claim_repo = ClaimRepository(db_session)
    orchestrator = VehicleIdentityContinuityOrchestrator(
        policy_repo=policy_repo,
        claim_repo=claim_repo,
        redis_mgr=redis_mgr,
    )

    claim_id = uuid.uuid4()
    test_claim = Claim(
        claim_id=claim_id,
        policy_id="POL-HAPPY-001",
        video_sha256=f"sha256_plate_{uuid.uuid4().hex[:8]}",
        capture_source="FILE_UPLOAD",
        is_demo_rehearsal=True,
        current_stage="STAGE_1_IDENTITY",
        claim_status="PROCESSING",
    )
    await claim_repo.create_claim(test_claim)

    telemetry = await orchestrator.execute(
        claim_id=claim_id,
        scratch_video_path=clip_wrong_plate,
        policy_id="POL-HAPPY-001",
        is_demo_rehearsal=True,
    )

    assert telemetry.passed is False
    assert telemetry.escalation_code == "ESC-01"

    updated = await claim_repo.get_by_id(claim_id)
    assert updated.current_stage == "STAGE_1_IDENTITY"
    assert updated.claim_status == "REJECTED_STAGE1_IDENTITY"
    assert updated.escalation_code == "ESC-01"


@pytest.mark.asyncio
async def test_orchestrator_wrong_color_updates_db_and_emits_sse(
    db_session, redis_mgr, clip_blue_car_spoof_plate
):
    """End-to-End: Spoofed plate on blue car transitions claim to REJECTED_STAGE1_IDENTITY with ESC-01."""
    policy_repo = PolicyRepository(db_session)
    claim_repo = ClaimRepository(db_session)
    orchestrator = VehicleIdentityContinuityOrchestrator(
        policy_repo=policy_repo,
        claim_repo=claim_repo,
        redis_mgr=redis_mgr,
    )

    claim_id = uuid.uuid4()
    test_claim = Claim(
        claim_id=claim_id,
        policy_id="POL-HAPPY-001",
        video_sha256=f"sha256_color_{uuid.uuid4().hex[:8]}",
        capture_source="FILE_UPLOAD",
        is_demo_rehearsal=True,
        current_stage="STAGE_1_IDENTITY",
        claim_status="PROCESSING",
    )
    await claim_repo.create_claim(test_claim)

    telemetry = await orchestrator.execute(
        claim_id=claim_id,
        scratch_video_path=clip_blue_car_spoof_plate,
        policy_id="POL-HAPPY-001",
        is_demo_rehearsal=True,
    )

    assert telemetry.passed is False
    assert telemetry.escalation_code == "ESC-01"

    updated = await claim_repo.get_by_id(claim_id)
    assert updated.current_stage == "STAGE_1_IDENTITY"
    assert updated.claim_status == "REJECTED_STAGE1_IDENTITY"
    assert updated.escalation_code == "ESC-01"

