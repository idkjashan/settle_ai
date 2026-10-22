"""
tests/test_real_videos.py
Integration tests validating Stage 0 (Fast-Fail Gate) and Stage 1 (Identity & Continuity Grounding)
on real-world exterior vehicle walkaround videos from test_assets/real_videos/.
"""
import json
from pathlib import Path
import cv2
import numpy as np
import pytest

from app.domain.fast_fail_gate.container_forensics import container_forensics_validator
from app.domain.fast_fail_gate.visual_quality_gate import visual_quality_validator
from app.domain.vehicle_identity_continuity.cut_detector import cut_detector
from app.domain.vehicle_identity_continuity.color_grounding_validator import color_grounding_validator
from app.domain.vehicle_identity_continuity.plate_ocr_validator import plate_ocr_validator
from app.domain.vehicle_identity_continuity.schemas import PolicyGroundingContext

REAL_VIDEOS_DIR = Path("/home/jashan/settleai/test_assets/videos/difficult")
MANIFEST_PATH = Path("/home/jashan/settleai/test_assets/videos/manifest.json")


@pytest.fixture(scope="session")
def real_videos_manifest():
    assert MANIFEST_PATH.exists(), f"Missing manifest at {MANIFEST_PATH}"
    data = json.loads(MANIFEST_PATH.read_text())
    diff_vids = data["categories"]["difficult"]["videos"]
    real_filenames = [
        "toyota_hilux_white_ute.mp4",
        "fiat_500_blue_hatchback.mp4",
        "vw_golf_grey_hatchback.mp4",
        "ferrari_360_silver_coupe.mp4",
    ]
    videos = []
    for fname in real_filenames:
        if fname in diff_vids:
            meta = dict(diff_vids[fname])
            meta["filepath"] = str(Path("/home/jashan/settleai/test_assets") / meta["rel_path"])
            videos.append(meta)
    return videos


class TestRealVideosStage0:
    """Stage 0 Fast-Fail Sanity Gate verification on real walkaround videos."""

    def test_real_videos_pass_container_forensics(self, real_videos_manifest):
        """All real walkaround videos meet container dimensions, framerate, and duration requirements."""
        for v in real_videos_manifest:
            video_path = Path(v["filepath"])
            assert video_path.exists(), f"Video file missing: {video_path}"
            file_size = video_path.stat().st_size

            report = container_forensics_validator.validate(
                video_path=video_path,
                sha256=f"sha_{v['filename']}",
                file_size_bytes=file_size,
            )
            assert report.passed is True, (
                f"Real video {v['filename']} failed container forensics! Codes: {report.failure_codes}"
            )
            assert report.width >= 720
            assert report.height >= 480
            assert report.duration_sec >= 15.0

    def test_real_videos_pass_visual_quality(self, real_videos_manifest):
        """All real walkaround videos have proper illumination (45 <= Y <= 220) and sharpness (Lap > 80)."""
        for v in real_videos_manifest:
            video_path = Path(v["filepath"])
            file_size = video_path.stat().st_size
            c_rep = container_forensics_validator.validate(video_path, "sha", file_size)

            v_rep = visual_quality_validator.validate(video_path, c_rep)
            assert v_rep.passed is True, (
                f"Real video {v['filename']} failed visual quality! Codes: {v_rep.failure_codes}"
            )
            assert len(v_rep.sampled_frames) == 5, f"Expected 5 temporal samples for {v['filename']}"
            assert 45.0 <= v_rep.mean_luminance_aggregate <= 220.0
            assert v_rep.mean_sharpness_aggregate >= 80.0


class TestRealVideosStage1Grounding:
    """Stage 1 Continuity & Color Grounding verification on real walkaround videos."""

    def test_real_videos_pass_cut_detector(self, real_videos_manifest):
        """Walkaround videos are continuous shots without artificial cuts or splices."""
        for v in real_videos_manifest:
            video_path = Path(v["filepath"])
            result = cut_detector.evaluate(video_path)
            assert result.is_continuous is True, (
                f"Real video {v['filename']} flagged discontinuous! Cuts: {result.cut_frame_indices}"
            )
            assert result.evaluated_frames >= 500, f"Expected full duration evaluation for {v['filename']}"
            assert len(result.cut_frame_indices) == 0

    def test_real_hilux_white_color_grounding(self):
        """Toyota Hilux matches WHITE policy color grounding and rejects wrong color."""
        video_path = REAL_VIDEOS_DIR / "toyota_hilux_white_ute.mp4"
        cap = cv2.VideoCapture(str(video_path))
        cap.set(cv2.CAP_PROP_POS_FRAMES, 300)
        ret, frame = cap.read()
        cap.release()
        assert ret is True

        yolo = plate_ocr_validator.get_yolo()
        results = yolo.predict(frame, imgsz=640, verbose=False, conf=0.35)
        boxes = results[0].boxes
        largest_box = None
        max_area = 0
        for b in boxes:
            if int(b.cls[0].item()) in (2, 5, 7):
                bx1, by1, bx2, by2 = [int(v.item()) for v in b.xyxy[0]]
                area = (bx2 - bx1) * (by2 - by1)
                if area > max_area:
                    max_area = area
                    largest_box = (bx1, by1, bx2, by2)

        assert largest_box is not None, "Failed to detect Hilux vehicle in frame 300"

        # Matching WHITE policy
        ctx_white = PolicyGroundingContext(
            policy_id="POL-HILUX-WHT",
            registration_number="1ILJ681",
            make="Toyota",
            model="Hilux",
            registered_color="WHITE",
        )
        res_white = color_grounding_validator.validate_paint_color(frame, largest_box, ctx_white)
        assert res_white.is_color_match is True
        assert res_white.failure_code is None

        # Mismatched RED policy
        ctx_red = PolicyGroundingContext(
            policy_id="POL-HILUX-RED",
            registration_number="1ILJ681",
            make="Toyota",
            model="Hilux",
            registered_color="RED",
        )
        res_red = color_grounding_validator.validate_paint_color(frame, largest_box, ctx_red)
        assert res_red.is_color_match is False
        assert res_red.failure_code == "S1_COLOR_MISMATCH"

    def test_real_golf_grey_color_grounding(self):
        """Volkswagen Golf matches GREY policy color grounding and rejects wrong color."""
        video_path = REAL_VIDEOS_DIR / "vw_golf_grey_hatchback.mp4"
        cap = cv2.VideoCapture(str(video_path))
        cap.set(cv2.CAP_PROP_POS_FRAMES, 100)
        ret, frame = cap.read()
        cap.release()
        assert ret is True

        yolo = plate_ocr_validator.get_yolo()
        results = yolo.predict(frame, imgsz=640, verbose=False, conf=0.35)
        boxes = results[0].boxes
        largest_box = None
        max_area = 0
        for b in boxes:
            if int(b.cls[0].item()) in (2, 5, 7):
                bx1, by1, bx2, by2 = [int(v.item()) for v in b.xyxy[0]]
                area = (bx2 - bx1) * (by2 - by1)
                if area > max_area:
                    max_area = area
                    largest_box = (bx1, by1, bx2, by2)

        assert largest_box is not None, "Failed to detect Golf vehicle in frame 100"

        ctx_grey = PolicyGroundingContext(
            policy_id="POL-GOLF-GRY",
            registration_number="GD73KZS",
            make="Volkswagen",
            model="Golf",
            registered_color="GREY",
        )
        res_grey = color_grounding_validator.validate_paint_color(frame, largest_box, ctx_grey)
        assert res_grey.is_color_match is True
        assert res_grey.failure_code is None

        ctx_blue = PolicyGroundingContext(
            policy_id="POL-GOLF-BLU",
            registration_number="GD73KZS",
            make="Volkswagen",
            model="Golf",
            registered_color="BLUE",
        )
        res_blue = color_grounding_validator.validate_paint_color(frame, largest_box, ctx_blue)
        assert res_blue.is_color_match is False
        assert res_blue.failure_code == "S1_COLOR_MISMATCH"
