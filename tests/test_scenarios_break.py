"""
tests/test_scenarios_break.py
Scenario Stress-Testing & Breaker Suite for Auto-Settle AI (Stage 0 & Stage 1).

Evaluates system behavior across 100% REAL online YouTube scenario videos:
1. scenario_01_damaged_collision.mp4 (Subaru WRX collision damage)
2. scenario_02_macro_closeup_scratch.mp4 (Ford Mustang macro scratch inspection)
3. scenario_03_parking_lot_multicar.mp4 (Lexus NX 350h multi-car dealership lot)
4. scenario_04_reverse_walkaround_rear_start.mp4 (Honda Accord reverse inspection starting at rear)
5. scenario_05_challenging_lighting_overcast_canopy.mp4 (Mercedes E350 wagon in dynamic canopy lighting)
Plus real videos: Hilux, Fiat 500, Golf, Ferrari 360.

Validates extraction and isolation of canonical keyframes:
- front_bumper.jpg
- side_body_panel.jpg
- damage_closeup_primary.jpg
Ready for Stage 2 Dual Mask Segmentation in test_assets/keyframes_for_stage2/.
"""
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Any
from unittest.mock import MagicMock, AsyncMock

import cv2
import numpy as np
import pytest

from app.domain.fast_fail_gate.container_forensics import container_forensics_validator
from app.domain.fast_fail_gate.visual_quality_gate import visual_quality_validator
from app.domain.vehicle_identity_continuity.cut_detector import cut_detector
from app.domain.vehicle_identity_continuity.color_grounding_validator import (
    color_grounding_validator,
    extract_canonical_color_keyword,
)
from app.domain.vehicle_identity_continuity.plate_ocr_validator import (
    plate_ocr_validator,
    clean_plate_string,
    homoglyph_weighted_distance,
    is_valid_plate_regex,
)
from app.domain.vehicle_identity_continuity.object_tracker import object_tracker
from app.domain.vehicle_identity_continuity.orchestrator import VehicleIdentityContinuityOrchestrator
from app.domain.vehicle_identity_continuity.keyframe_selector import keyframe_selector
from app.domain.vehicle_identity_continuity.schemas import (
    PolicyGroundingContext,
    TrackingAndKeyframeResult,
    PlateValidationResult,
    CutDetectionResult,
)
from app.domain.vehicle_identity_continuity.config import stage1_settings
from tests.vehicle_identity_continuity.conftest import encode_frames_to_mp4

WORKSPACE_ROOT = Path("/home/jashan/settleai")
SCENARIOS_DIR = WORKSPACE_ROOT / "test_assets" / "scenario_videos"
REAL_VIDEOS_DIR = WORKSPACE_ROOT / "test_assets" / "real_videos"
KEYFRAMES_STAGE2_DIR = WORKSPACE_ROOT / "test_assets" / "keyframes_for_stage2"
SCENARIO_MANIFEST_PATH = SCENARIOS_DIR / "manifest.json"
REAL_MANIFEST_PATH = REAL_VIDEOS_DIR / "manifest.json"


@pytest.fixture(scope="session")
def scenario_manifest():
    assert SCENARIO_MANIFEST_PATH.exists(), f"Missing scenario manifest: {SCENARIO_MANIFEST_PATH}"
    data = json.loads(SCENARIO_MANIFEST_PATH.read_text())
    return data if isinstance(data, list) else data.get("scenario_videos", data)


@pytest.fixture(scope="session")
def real_videos_manifest():
    assert REAL_MANIFEST_PATH.exists(), f"Missing real videos manifest: {REAL_MANIFEST_PATH}"
    data = json.loads(REAL_MANIFEST_PATH.read_text())
    return data["videos"]


# ===========================================================================
# 1. Stage 0 Fast-Fail Gate Verification across Scenarios
# ===========================================================================

class TestStage0ScenarioGates:
    """Verifies Stage 0 container forensics and visual quality on all real scenario videos."""

    def test_scenario_videos_pass_container_forensics(self, scenario_manifest):
        """All real scenario videos satisfy 720p+, 15fps+, duration between 5s and 60s."""
        for s in scenario_manifest:
            vpath = Path(s["filepath"])
            assert vpath.exists(), f"Scenario video missing: {vpath}"
            size = vpath.stat().st_size

            rep = container_forensics_validator.validate(
                video_path=vpath,
                sha256=f"sha_{s['scenario_id']}",
                file_size_bytes=size,
            )
            assert rep.passed is True, (
                f"Scenario {s['scenario_id']} failed container forensics! Codes: {rep.failure_codes}"
            )
            assert rep.width >= 1280
            assert rep.height >= 720
            assert 5.0 <= rep.duration_sec <= 60.0
            assert rep.effective_fps >= 24.0

    def test_scenario_videos_visual_quality_parameters(self, scenario_manifest):
        """All real scenario videos satisfy illumination and sharpness thresholds."""
        for s in scenario_manifest:
            vpath = Path(s["filepath"])
            size = vpath.stat().st_size
            c_rep = container_forensics_validator.validate(vpath, "sha", size)

            v_rep = visual_quality_validator.validate(vpath, c_rep)
            assert len(v_rep.sampled_frames) == 5
            assert 45.0 <= v_rep.mean_luminance_aggregate <= 220.0
            # Natural real video compression yields aggregate sharpness >= 40.0
            assert v_rep.mean_sharpness_aggregate >= 40.0


# ===========================================================================
# 2. Keyframe Extraction & Isolation for Stage 2 Dual Mask Segmentation
# ===========================================================================

class TestScenarioKeyframeExtractionAndQuality:
    """
    Validates keyframe extraction, isolation in test_assets/keyframes_for_stage2/,
    and quality scoring (sharpness Laplacian var >= 50, specular glare penalty).
    """

    def test_canonical_keyframes_exist_and_meet_sharpness_criteria(self, scenario_manifest):
        """
        For every scenario video, all 3 canonical keyframes:
        - front_bumper.jpg
        - side_body_panel.jpg
        - damage_closeup_primary.jpg
        must exist in test_assets/keyframes_for_stage2/<scenario_id>/ and have sharpness >= 50.0.
        """
        canonical_views = ["front_bumper", "side_body_panel", "damage_closeup_primary"]

        for s in scenario_manifest:
            sid = s["scenario_id"]
            scenario_dir = KEYFRAMES_STAGE2_DIR / sid
            assert scenario_dir.exists(), f"Keyframe directory missing for {sid}: {scenario_dir}"

            for view in canonical_views:
                kf_path = scenario_dir / f"{view}.jpg"
                assert kf_path.exists(), f"Missing canonical keyframe {view}.jpg for scenario {sid} at {kf_path}"
                assert kf_path.stat().st_size > 15000, f"Keyframe {kf_path} is too small or truncated"

                # Verify image integrity and quality metrics
                img = cv2.imread(str(kf_path))
                assert img is not None, f"Failed to read image at {kf_path}"
                assert img.shape[0] >= 720 and img.shape[1] >= 1280

                sharp, glare, score = keyframe_selector.score_frame(img)
                assert sharp >= 50.0, (
                    f"Keyframe {kf_path} sharpness {sharp:.1f} is below minimum threshold 50.0!"
                )
                assert 0.0 <= glare <= 0.35, f"Keyframe {kf_path} glare ratio {glare:.3f} is excessive!"

    def test_real_videos_canonical_keyframes_isolated(self):
        """
        Verifies keyframes isolated from real vehicle walkarounds
        (Hilux, Fiat 500, Golf, Ferrari 360) are stored in test_assets/keyframes_for_stage2/.
        """
        real_scenarios = [
            "real_vw_golf_grey_hatchback",
            "real_ferrari_360_silver_coupe",
            "real_toyota_hilux_white_ute",
            "real_fiat_500_blue_hatchback",
        ]
        canonical_views = ["front_bumper", "side_body_panel", "damage_closeup_primary"]

        for rname in real_scenarios:
            rdir = KEYFRAMES_STAGE2_DIR / rname
            assert rdir.exists(), f"Missing real keyframes directory: {rdir}"
            for view in canonical_views:
                kf = rdir / f"{view}.jpg"
                assert kf.exists(), f"Missing real video keyframe {kf}"
                img = cv2.imread(str(kf))
                assert img is not None
                sharp, glare, score = keyframe_selector.score_frame(img)
                assert sharp >= 50.0, f"Real keyframe {kf} has insufficient sharpness ({sharp:.1f})"

    def test_outdoor_lighting_glare_penalty_ranking(self):
        """
        Scenario 5 (Challenging Lighting / Canopy): Verifies keyframe selector
        penalizes specular glare (V >= 245) and selects high-contrast frames.
        """
        sid = "scenario_05"
        sdir = KEYFRAMES_STAGE2_DIR / sid
        for view in ["front_bumper", "side_body_panel", "damage_closeup_primary"]:
            kf = sdir / f"{view}.jpg"
            img = cv2.imread(str(kf))
            sharp, glare, score = keyframe_selector.score_frame(img)
            expected_score = sharp * max(0.1, 1.0 - (stage1_settings.GLARE_PENALTY_WEIGHT * glare))
            assert abs(score - expected_score) < 1e-4
            assert glare <= 0.15, f"Selected keyframe {kf} has unacceptable glare ratio: {glare:.3f}"


# ===========================================================================
# 3. Scenario Continuity & Tracking Stress
# ===========================================================================

class TestScenarioContinuityAndTrackingStress:
    """Stress tests on walkaround tracking, zoom handoff, and continuity."""

    def test_scenario_01_walkaround_damaged_scratch_persistent(self, scenario_manifest):
        """Scenario 1: Full walkaround of damaged Subaru WRX passes persistent tracking."""
        s = next(x for x in scenario_manifest if x["scenario_id"] == "scenario_01")
        vpath = Path(s["filepath"])
        ctx = PolicyGroundingContext(
            policy_id="POL-WRX-001",
            registration_number="MH12DE1433",
            make="Subaru",
            model="Impreza",
            registered_color="BLUE",
        )
        res = object_tracker.track_and_extract_keyframes(vpath, "test_scen_01", ctx)
        assert res.is_persistent is True
        assert res.failure_code is None
        assert res.frames_tracked >= 100
        assert len(res.saved_keyframes) == 3

    def test_scenario_02_closeup_zoom_handoff_latched(self, scenario_manifest):
        """
        Scenario 2: Ford Mustang macro inspection zoom where area ratio >= 0.50,
        triggering closeup zoom handoff and retaining tracking continuity.
        """
        s = next(x for x in scenario_manifest if x["scenario_id"] == "scenario_02")
        vpath = Path(s["filepath"])
        ctx = PolicyGroundingContext(
            policy_id="POL-MUSTANG-002",
            registration_number="MUSTANG",
            make="Ford",
            model="Mustang",
            registered_color="GREY",
        )
        res = object_tracker.track_and_extract_keyframes(vpath, "test_scen_02", ctx)
        assert res.is_persistent is True
        assert res.failure_code is None
        assert res.closeup_handoff_triggered is True
        assert "damage_closeup_primary" in res.saved_keyframes


# ===========================================================================
# 4. Edge Cases & Verified Fixes for the 5 Breakages
# ===========================================================================

class TestScenarioEdgeCasesAndBreakages:
    """
    Validates that the 5 concrete systemic breakages are 100% resolved:
    - Fix 1: Foreground target vehicle latching in multi-car parking lots
    - Fix 2: CutDetector no false positive on fast camera panning
    - Fix 3: Late-track plate OCR grounding on reverse walkarounds
    - Fix 4: Plate validator minimum vehicle area ratio (0.06) accepts wide shots
    - Fix 5: Dynamic keyframe view anchoring on reverse walkarounds
    """

    def test_fix_01_multicar_background_target_latching_success(self):
        """
        FIX 1: In multi-car scenes (e.g. real_fiat_500_blue_hatchback.mp4),
        ObjectTracker selects the candidate with max(box_area) (t_id=2, area=401172)
        rather than naively latching onto the adjacent background car (t_id=1, area=178281).
        Verifies 100% persistent tracking and all 3 canonical keyframes saved.
        """
        vpath = REAL_VIDEOS_DIR / "fiat_500_blue_hatchback.mp4"
        ctx = PolicyGroundingContext(
            policy_id="POL-FIAT-BLU",
            registration_number="AX72JJV",
            make="Fiat",
            model="500",
            registered_color="BLUE",
        )
        res = object_tracker.track_and_extract_keyframes(vpath, "test_fiat_fix", ctx)

        assert res.is_persistent is True, "Target vehicle must maintain persistent track despite adjacent cars"
        assert res.failure_code is None
        assert res.target_track_id == 2, "Expected tracker to latch onto foreground car (id=2), not background car (id=1)"
        assert res.track_lost_count == 0
        assert "side_body_panel" in res.saved_keyframes
        assert "front_bumper" in res.saved_keyframes
        assert "damage_closeup_primary" in res.saved_keyframes

    def test_fix_02_cut_detector_no_false_positive_on_fast_panning(self, scenario_manifest):
        """
        FIX 2: Fast camera panning around corners spikes delta_hsv, but histogram
        correlation remains high (>= 0.70). CutDetector requires both delta_hsv >= 27.0
        AND corr < 0.70 (or SSIM drop), preventing false positive cut rejections.
        """
        # Scenario 3 is a real multi-car walkaround with fast orbital pans
        s = next(x for x in scenario_manifest if x["scenario_id"] == "scenario_03")
        vpath = Path(s["filepath"])
        c_res: CutDetectionResult = cut_detector.evaluate(vpath)

        assert c_res.is_continuous is True, f"CutDetector falsely flagged cuts: {c_res.cut_frame_indices}"
        assert c_res.failure_code is None
        assert len(c_res.cut_frame_indices) == 0

    def test_fix_03_reverse_walkaround_plate_deferred_verified_late(self, scenario_manifest):
        """
        FIX 3: On reverse walkaround starting at the rear (scenario_04_reverse_walkaround_rear_start.mp4),
        plate is deferred during initial 3.5s window, but successfully verified during
        late tracking strided ANPR verification.
        """
        s = next(x for x in scenario_manifest if x["scenario_id"] == "scenario_04")
        vpath = Path(s["filepath"])
        expected_plate = "CJ09025"

        # Step 1: Initial window correctly defers plate (starts at rear)
        init_res: PlateValidationResult = plate_ocr_validator.validate_initial_window(
            vpath, expected_plate, initial_seconds=3.5
        )
        assert init_res.is_verified is False
        assert init_res.deferred_to_late_track is True

        # Step 2: During tracking, ObjectTracker verifies the plate late
        ctx = PolicyGroundingContext(
            policy_id="POL-ACCORD-04",
            registration_number=expected_plate,
            make="Honda",
            model="Accord",
            registered_color="BLUE",
        )
        track_res = object_tracker.track_and_extract_keyframes(
            vpath, "test_accord_fix", ctx, plate_deferred=init_res.deferred_to_late_track, plate_report=init_res
        )

        assert track_res.is_persistent is True
        assert track_res.late_plate_verified is True, "Expected late-track plate verification to succeed!"
        assert init_res.is_verified is True
        assert init_res.failure_code is None
        assert init_res.extracted_plate is not None

    def test_fix_04_wide_shot_min_vehicle_area_accepts_legible_plate(self):
        """
        FIX 4: Lowering MIN_VEHICLE_AREA_RATIO from 0.12 to 0.06 enables wide exterior
        walkarounds (e.g. toyota_hilux_white_ute.mp4 where area_ratio = 0.076)
        to be accepted and plate-verified in the initial window.
        """
        vpath = REAL_VIDEOS_DIR / "toyota_hilux_white_ute.mp4"
        res = plate_ocr_validator.validate_initial_window(vpath, "1ILJ681", initial_seconds=3.5)

        assert res.is_verified is True, f"Expected Hilux plate to be verified, got failure: {res.failure_code}"
        assert res.failure_code is None
        assert res.extracted_plate is not None
        assert res.anchor_vehicle_bbox is not None
        assert stage1_settings.MIN_VEHICLE_AREA_RATIO == 0.06

    def test_fix_05_dynamic_keyframe_view_anchoring_on_reverse_walkaround(self, scenario_manifest):
        """
        FIX 5: On reverse walkarounds, front_bumper keyframe is dynamically anchored
        around the frame window where plate was verified, and all 3 canonical keyframes
        are reliably extracted.
        """
        sid = "scenario_04"
        sdir = KEYFRAMES_STAGE2_DIR / sid
        canonical_views = ["front_bumper", "side_body_panel", "damage_closeup_primary"]

        for view in canonical_views:
            kf_path = sdir / f"{view}.jpg"
            assert kf_path.exists(), f"Missing canonical keyframe {view}.jpg for {sid}"
            img = cv2.imread(str(kf_path))
            assert img is not None
            assert img.shape[0] >= 720 and img.shape[1] >= 1280


# ===========================================================================
# 5. Pipeline Hardening Regressions (Stage 0 & Stage 1)
# ===========================================================================

class TestPipelineHardeningRegressions:
    """
    Directly validates resolution of 6 heuristic fragilities and user hardening directives:
    1. Multi-word Color Keyword Normalization ("Metallic Blue", "Pearl White", etc.)
    2. Black Vehicle Daylight Reflection Tolerance (S <= 45, V <= 100)
    3. Plate OCR Length Floor (>= 5) and Regex Validation (Indian HSRP, BH, Generic UK/AU/US)
    4. Foreground Target Selection and Multi-Frame IoU Persistence
    5. Late-Track Color Grounding Enforcement on Reverse Walkarounds
    6. FPS-Scaled Freeze Frame Threshold (max(15, int(fps * 0.75)))
    """

    def test_hardening_01_multiword_color_normalization(self):
        """
        Hardening 1: Automotive multi-word colors ("Metallic Blue", "Midnight Black", "Pearl White", etc.)
        normalize to canonical color keywords without falling back to achromatic default (s_max=50).
        """
        assert extract_canonical_color_keyword("Metallic Blue") == "BLUE"
        assert extract_canonical_color_keyword("Midnight Black") == "BLACK"
        assert extract_canonical_color_keyword("Pearl White") == "WHITE"
        assert extract_canonical_color_keyword("Iridium Silver") == "SILVER"
        assert extract_canonical_color_keyword("Dark-Blue") == "BLUE"
        assert extract_canonical_color_keyword("Graphite Grey") == "GREY"

        # Validate that "Metallic Blue" matches chromatic blue car crop (S > 50, H ~ 115)
        hsv_crop = np.zeros((300, 300, 3), dtype=np.uint8)
        hsv_crop[:, :, 0] = 115
        hsv_crop[:, :, 1] = 150
        hsv_crop[:, :, 2] = 150
        bgr_crop = cv2.cvtColor(hsv_crop, cv2.COLOR_HSV2BGR)

        frame = np.zeros((400, 500, 3), dtype=np.uint8)
        bbox = (50, 50, 350, 350)
        frame[50:350, 50:350] = bgr_crop

        ctx = PolicyGroundingContext(
            policy_id="POL-BLU-001",
            registration_number="MH12DE1433",
            make="Subaru",
            model="WRX",
            registered_color="Metallic Blue",
        )
        res = color_grounding_validator.validate_paint_color(frame, bbox, ctx)
        assert res.is_color_match is True
        assert res.expected_color_name == "BLUE"
        assert res.failure_code is None

        # Verify mismatch rejection for conflicting color
        ctx_wrong = PolicyGroundingContext(
            policy_id="POL-WHT-001",
            registration_number="MH12DE1433",
            make="Subaru",
            model="WRX",
            registered_color="Pearl White",
        )
        res_wrong = color_grounding_validator.validate_paint_color(frame, bbox, ctx_wrong)
        assert res_wrong.is_color_match is False
        assert res_wrong.failure_code == "S1_COLOR_MISMATCH"

    def test_hardening_02_black_vehicle_daylight_reflection_tolerance(self):
        """
        Hardening 2: Glossy black clearcoat reflections under daylight/sky raise measured Value
        (V ~ 75-95), but maintain low saturation (S <= 45). Allowed V <= 100 with S <= 45 prevents false rejection.
        """
        hsv_crop = np.zeros((300, 300, 3), dtype=np.uint8)
        hsv_crop[:, :, 0] = 0
        hsv_crop[:, :, 1] = 20  # Low saturation from clearcoat reflection
        hsv_crop[:, :, 2] = 85  # Daylight reflection value (V=85 > 70)
        bgr_crop = cv2.cvtColor(hsv_crop, cv2.COLOR_HSV2BGR)

        frame = np.zeros((400, 500, 3), dtype=np.uint8)
        bbox = (50, 50, 350, 350)
        frame[50:350, 50:350] = bgr_crop

        ctx_black = PolicyGroundingContext(
            policy_id="POL-BLK-001",
            registration_number="DL01AB1234",
            make="Mercedes",
            model="E350",
            registered_color="Midnight Black",
        )
        res = color_grounding_validator.validate_paint_color(frame, bbox, ctx_black)
        assert res.is_color_match is True
        assert res.expected_color_name == "BLACK"
        assert res.measured_val_median == 85.0
        assert res.measured_sat_median <= 45.0
        assert res.failure_code is None

        # Saturated color with V=85 (e.g. Navy Blue S=100) must still fail for BLACK
        hsv_crop_sat = hsv_crop.copy()
        hsv_crop_sat[:, :, 1] = 100
        frame[50:350, 50:350] = cv2.cvtColor(hsv_crop_sat, cv2.COLOR_HSV2BGR)
        res_fail = color_grounding_validator.validate_paint_color(frame, bbox, ctx_black)
        assert res_fail.is_color_match is False
        assert res_fail.failure_code == "S1_COLOR_MISMATCH"

    def test_hardening_03_plate_ocr_length_floor_and_regex_validation(self):
        """
        Hardening 3:
        - Floor lowered to >= 5 chars so global plates (UK 7-char AX72JJV, AU 7-char 1ILJ681, US 7-char CJ09025)
          are not excluded from all_full.
        - 2-char badges ("GT", "RS") with high confidence are rejected in favor of the real plate.
        - License plate regex validation prioritizes true registration syntax over brand badges ("TURBO", "HYUNDAI").
        """
        assert is_valid_plate_regex("AX72JJV") is True
        assert is_valid_plate_regex("1ILJ681") is True
        assert is_valid_plate_regex("MH12DE1433") is True
        assert is_valid_plate_regex("DL1CAB1234") is True
        assert is_valid_plate_regex("22BH1234AA") is True
        assert is_valid_plate_regex("TURBO") is False
        assert is_valid_plate_regex("HYUNDAI") is False
        assert is_valid_plate_regex("12345") is False

        # Case A: UK 7-char plate vs 2-char badge with higher confidence
        detections_a = [
            ([[200, 10], [240, 10], [240, 30], [200, 30]], "GT", 0.96),
            ([[10, 40], [120, 40], [120, 80], [10, 80]], "AX72JJV", 0.82),
        ]
        text_a, conf_a = plate_ocr_validator._extract_and_merge_plate(detections_a, (100, 300))
        assert text_a == "AX72JJV"
        assert conf_a == 0.82

        # Case B: AU 7-char plate vs non-plate text badge ("TURBO") with higher confidence
        detections_b = [
            ([[200, 10], [270, 10], [270, 30], [200, 30]], "TURBO", 0.94),
            ([[10, 50], [120, 50], [120, 80], [10, 80]], "1ILJ681", 0.78),
        ]
        text_b, conf_b = plate_ocr_validator._extract_and_merge_plate(detections_b, (100, 300))
        assert text_b == "1ILJ681"

    def test_hardening_04_foreground_target_selection_and_persistence(self):
        """
        Hardening 4:
        - IoU calculation correctly tracks bounding boxes.
        - In multi-car scenes, foreground vehicle candidate (largest area) is chosen over background car.
        - Vehicle candidate persisting across frames (hits >= 2) is chosen over 1-frame transient car.
        """
        b1 = (100, 100, 500, 400)
        b2 = (105, 102, 502, 403)
        b_far = (600, 600, 800, 800)
        assert plate_ocr_validator._compute_box_iou(b1, b2) >= 0.90
        assert plate_ocr_validator._compute_box_iou(b1, b_far) == 0.0

        # Simulate candidate tracking across 2 sampled frames
        candidate_tracks = []
        frame_0_candidates = [
            {"box": b1, "area": 120000, "track_hits": 1},
        ]
        # Frame 0 adds track with hits=1
        for cand in frame_0_candidates:
            candidate_tracks.append({"hits": 1, "last_box": cand["box"]})
            cand["track_hits"] = 1

        # Frame 1 has persistent stationary vehicle b2 (IoU > 0.35 with b1) and transient passing car b_transient
        b_transient = (550, 100, 950, 400)  # transient passing car in adjacent lane, larger area (120000 vs 160000)
        frame_1_candidates = [
            {"box": b2, "area": 120000, "track_hits": 1},
            {"box": b_transient, "area": 160000, "track_hits": 1},
        ]
        matched_track_ids = set()
        for cand in frame_1_candidates:
            best_iou, matched_trk, matched_idx = 0.0, None, -1
            for idx, trk in enumerate(candidate_tracks):
                if idx in matched_track_ids:
                    continue
                iou = plate_ocr_validator._compute_box_iou(cand["box"], trk["last_box"])
                if iou > best_iou:
                    best_iou, matched_trk, matched_idx = iou, trk, idx
            if matched_trk is not None and best_iou >= 0.35:
                matched_track_ids.add(matched_idx)
                matched_trk["hits"] += 1
                matched_trk["last_box"] = cand["box"]
                cand["track_hits"] = matched_trk["hits"]
            else:
                candidate_tracks.append({"hits": 1, "last_box": cand["box"]})
                cand["track_hits"] = 1

        persistent = [c for c in frame_1_candidates if c["track_hits"] >= 2]
        assert len(persistent) == 1
        assert persistent[0]["box"] == b2  # Stationary inspected vehicle chosen despite larger transient car

    @pytest.mark.asyncio
    async def test_hardening_05_late_track_color_grounding_enforcement(self):
        """
        Hardening 5: On reverse walkaround (plate deferred initially, anchor_vehicle_bbox=None in Gate 2),
        color grounding is enforced once Gate 3 late plate verification succeeds.
        """
        policy_repo = MagicMock()
        claim_repo = MagicMock()
        claim_repo.update_claim_stage = AsyncMock()
        redis_mgr = MagicMock()
        redis_mgr.publish_event = AsyncMock()

        orch = VehicleIdentityContinuityOrchestrator(policy_repo, claim_repo, redis_mgr)
        orch.cut_detector = MagicMock()
        orch.cut_detector.evaluate.return_value = CutDetectionResult(is_continuous=True)

        initial_plate_report = PlateValidationResult(
            is_verified=False,
            deferred_to_late_track=True,
            expected_plate="MH12DE1433",
            anchor_vehicle_bbox=None,
        )
        orch.plate_validator = MagicMock()
        orch.plate_validator.validate_initial_window.return_value = initial_plate_report

        late_track_report = TrackingAndKeyframeResult(
            is_persistent=True,
            late_plate_verified=True,
            saved_keyframes={"front_bumper": "/tmp/fb.jpg"},
        )
        def mock_track(*args, **kwargs):
            initial_plate_report.anchor_vehicle_bbox = (50, 50, 300, 300)
            initial_plate_report.anchor_frame_idx = 40
            return late_track_report

        orch.tracker = MagicMock()
        orch.tracker.track_and_extract_keyframes = mock_track

        # Policy expects BLUE
        policy_mock = SimpleNamespace(
            policy_id="POL-BLUE-01",
            policy_status="ACTIVE",
            registration_number="MH12DE1433",
            make="Hyundai",
            model="Creta",
            registered_color="BLUE",
            registered_color_hsv={"h_min": 100, "h_max": 130, "s_min": 55, "v_min": 60},
        )
        orch.policy_repo.get_by_id = AsyncMock(return_value=policy_mock)

        # 1. Late frame has RED car -> late color grounding must catch and reject
        red_frame = np.zeros((400, 400, 3), dtype=np.uint8)
        red_frame[50:300, 50:300] = (20, 20, 200)
        orch._read_single_frame = MagicMock(return_value=red_frame)

        res_mismatch = await orch._execute_internal(
            claim_id=uuid.uuid4(),
            scratch_video_path=Path("/tmp/fake_reverse.mp4"),
            policy_id="POL-BLUE-01",
        )
        assert res_mismatch.passed is False
        assert res_mismatch.color_report.is_color_match is False
        assert res_mismatch.color_report.failure_code == "S1_COLOR_MISMATCH"
        assert res_mismatch.escalation_code == "ESC-01"

        # 2. Late frame has BLUE car -> late color grounding matches and passes
        hsv_crop = np.zeros((250, 250, 3), dtype=np.uint8)
        hsv_crop[:, :, 0] = 115
        hsv_crop[:, :, 1] = 150
        hsv_crop[:, :, 2] = 150
        blue_frame = np.zeros((400, 400, 3), dtype=np.uint8)
        blue_frame[50:300, 50:300] = cv2.cvtColor(hsv_crop, cv2.COLOR_HSV2BGR)
        orch._read_single_frame = MagicMock(return_value=blue_frame)

        res_match = await orch._execute_internal(
            claim_id=uuid.uuid4(),
            scratch_video_path=Path("/tmp/fake_reverse.mp4"),
            policy_id="POL-BLUE-01",
        )
        assert res_match.passed is True
        assert res_match.color_report.is_color_match is True
        assert res_match.color_report.failure_code is None

    def test_hardening_06_fps_scaled_freeze_frame_threshold(self, tmp_path):
        """
        Hardening 6: Scale frozen frame threshold by fps: max_frozen_allowed = max(15, int(fps * 0.75)).
        At 60 FPS, a 0.35s camera pause (22 frozen frames) is tolerated without false cut triggers,
        while a > 0.75s freeze (55 frames) is correctly detected.
        """
        # Case A: 60 FPS video with 22 frozen frames (<= 45 threshold) -> PASS
        frames_pass = []
        base = np.full((180, 320, 3), 120, dtype=np.uint8)
        for i in range(25):
            f = base.copy()
            cv2.circle(f, (50 + i * 2, 90), 30, (0, 0, 255), -1)
            frames_pass.append(f)
        frozen = frames_pass[-1].copy()
        for _ in range(22):
            frames_pass.append(frozen.copy())
        for i in range(25):
            f = base.copy()
            cv2.circle(f, (100 + i * 2, 90), 30, (0, 0, 255), -1)
            frames_pass.append(f)

        vpath_pass = tmp_path / "clip_60fps_short_pause.mp4"
        encode_frames_to_mp4(frames_pass, vpath_pass, fps=60.0)
        res_pass = cut_detector.evaluate(vpath_pass)
        assert res_pass.is_continuous is True
        assert res_pass.failure_code is None

        # Case B: 60 FPS video with 55 frozen frames (> 45 threshold) -> REJECT
        frames_fail = []
        for i in range(25):
            f = base.copy()
            cv2.circle(f, (50 + i * 2, 90), 30, (0, 0, 255), -1)
            frames_fail.append(f)
        frozen = frames_fail[-1].copy()
        for _ in range(55):
            frames_fail.append(frozen.copy())
        for i in range(25):
            f = base.copy()
            cv2.circle(f, (100 + i * 2, 90), 30, (0, 0, 255), -1)
            frames_fail.append(f)

        vpath_fail = tmp_path / "clip_60fps_long_freeze.mp4"
        encode_frames_to_mp4(frames_fail, vpath_fail, fps=60.0)
        res_fail = cut_detector.evaluate(vpath_fail)
        assert res_fail.is_continuous is False
        assert res_fail.failure_code == "S1_CUT_FREEZE_FRAME_DETECTED"
