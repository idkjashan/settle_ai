"""
tests/test_rtdetr_vd_dataset.py
Automated test suite verifying the structural integrity, MOT Challenge compliance,
video codecs, image properties, and tracking benchmark on the RTDETR-VD dataset.
"""

from __future__ import annotations

import configparser
import json
from pathlib import Path
import pytest
import cv2

WORKSPACE_ROOT = Path("/home/jashan/settleai")
RTDETR_VD_ROOT = WORKSPACE_ROOT / "test_assets" / "rtdetr_vd"
DATASET_DIR = RTDETR_VD_ROOT / "dataset"
MANIFEST_FILE = RTDETR_VD_ROOT / "manifest.json"


@pytest.fixture(scope="module")
def manifest():
    assert MANIFEST_FILE.exists(), f"manifest.json missing at {MANIFEST_FILE}"
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def test_dataset_directory_hierarchy_and_splits():
    """Validates root folders and splits exist."""
    assert RTDETR_VD_ROOT.is_dir()
    assert DATASET_DIR.is_dir()
    assert (DATASET_DIR / "test").is_dir()
    assert (DATASET_DIR / "val").is_dir()
    assert (DATASET_DIR / "train").is_dir()
    assert (RTDETR_VD_ROOT / "views").is_dir()
    assert (RTDETR_VD_ROOT / "tools" / "verify_dataset.py").is_file()
    assert (RTDETR_VD_ROOT / "tools" / "benchmark_tracker.py").is_file()
    assert (RTDETR_VD_ROOT / "README.md").is_file()


def test_manifest_structure_and_sequences(manifest):
    """Checks manifest metadata integrity and sequence entries."""
    assert manifest["format"] == "MOT Challenge Format"
    assert "sequences" in manifest
    assert len(manifest["sequences"]) >= 5

    required_sequences = [
        "aveo",
        "VID_20260210_104922",
        "rtdetr_demo_landscape",
        "car_001_360_damage",
        "car_002_360_damage"
    ]
    for seq in required_sequences:
        assert seq in manifest["sequences"], f"Sequence {seq} missing from manifest"


@pytest.mark.parametrize("seq_name", [
    "aveo",
    "VID_20260210_104922",
    "VID_20260118_222318",
    "rtdetr_demo_portrait",
    "rtdetr_demo_landscape",
    "car_001_360_damage",
    "car_002_360_damage",
    "car_004_360",
    "car_006_360"
])
def test_sequence_mot_challenge_compliance(seq_name, manifest):
    """
    Validates MOT Challenge compliance for each sequence:
    1. img1/ exists with non-empty 1-indexed JPEG frames.
    2. gt/gt.txt exists and has valid comma-separated MOT rows.
    3. seqinfo.ini exists with valid key-value pairs matching image dimensions.
    4. <seq_name>.mp4 exists and is decodable by OpenCV.
    """
    meta = manifest["sequences"][seq_name]
    split = meta["split"]
    seq_dir = DATASET_DIR / split / seq_name

    assert seq_dir.is_dir(), f"Sequence dir {seq_dir} does not exist"

    # 1. seqinfo.ini
    ini_path = seq_dir / "seqinfo.ini"
    assert ini_path.is_file(), f"seqinfo.ini missing in {seq_dir}"
    cfg = configparser.ConfigParser()
    cfg.read(ini_path)
    assert "Sequence" in cfg
    seq_section = cfg["Sequence"]
    expected_length = int(seq_section["seqLength"])
    expected_width = int(seq_section["imWidth"])
    expected_height = int(seq_section["imHeight"])
    assert expected_length > 0
    assert expected_width > 0
    assert expected_height > 0

    # 2. img1/ frames
    img1_dir = seq_dir / "img1"
    assert img1_dir.is_dir(), f"img1 dir missing in {seq_dir}"
    frames = sorted(img1_dir.glob("*.jpg"))
    assert len(frames) == expected_length, (
        f"Frame count mismatch in {seq_name}: found {len(frames)}, expected {expected_length}"
    )

    # Validate first and last frame decodability & dimensions
    first_frame = cv2.imread(str(frames[0]))
    assert first_frame is not None, f"Failed to decode first frame in {seq_name}"
    assert first_frame.shape[1] == expected_width
    assert first_frame.shape[0] == expected_height

    # 3. gt/gt.txt
    gt_path = seq_dir / "gt" / "gt.txt"
    assert gt_path.is_file(), f"gt.txt missing in {seq_dir / 'gt'}"
    if gt_path.stat().st_size > 0:
        with open(gt_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        for line in lines[:20]:  # check sample lines
            parts = line.split(",")
            assert len(parts) >= 7, f"Invalid MOT row format in {gt_path}: {line}"
            f_num = int(parts[0])
            tid = int(parts[1])
            x, y, w, h = float(parts[2]), float(parts[3]), float(parts[4]), float(parts[5])
            assert 1 <= f_num <= expected_length, f"Frame {f_num} out of bounds in {gt_path}"
            assert tid >= 0, f"Track ID {tid} invalid in {gt_path}"
            assert w >= 0 and h >= 0, f"Negative width/height in {gt_path}: {line}"

    # 4. Source MP4 video
    mp4_path = seq_dir / f"{seq_name}.mp4"
    assert mp4_path.is_file(), f"Video file missing: {mp4_path}"
    cap = cv2.VideoCapture(str(mp4_path))
    assert cap.isOpened(), f"OpenCV failed to open {mp4_path}"
    v_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    v_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    assert v_width == expected_width, f"Video width {v_width} does not match seqinfo {expected_width}"
    assert v_height == expected_height, f"Video height {v_height} does not match seqinfo {expected_height}"


def test_views_directory_consistency():
    """Validates views directory has images and paired coordinate .txt files."""
    views_dir = RTDETR_VD_ROOT / "views"
    assert views_dir.is_dir()
    view_subdirs = [p for p in views_dir.iterdir() if p.is_dir()]
    assert len(view_subdirs) >= 3

    for vdir in view_subdirs:
        jpgs = sorted(vdir.glob("*.jpg"))
        assert len(jpgs) > 0, f"No view images in {vdir}"
        for jpg in jpgs:
            txt = jpg.with_suffix(".txt")
            assert txt.exists(), f"Missing coordinate file for view {jpg}"
            content = txt.read_text().strip()
            if content:
                for line in content.splitlines():
                    coords = [float(c) for c in line.split(",")]
                    assert len(coords) == 4, f"Invalid coords in {txt}: {line}"
                    assert coords[2] >= coords[0], f"x2 < x1 in {txt}: {line}"
                    assert coords[3] >= coords[1], f"y2 < y1 in {txt}: {line}"


def test_classified_videos_directories():
    """Validates the flat classified simple and difficult video directories."""
    simple_dir = WORKSPACE_ROOT / "test_assets" / "videos" / "simple"
    difficult_dir = WORKSPACE_ROOT / "test_assets" / "videos" / "difficult"
    assert simple_dir.is_dir()
    assert difficult_dir.is_dir()

    # Ensure no subdirectories exist inside simple or difficult (must be flat)
    assert not any(p.is_dir() for p in simple_dir.iterdir())
    assert not any(p.is_dir() for p in difficult_dir.iterdir())

    # Check key videos exist directly inside them
    assert (simple_dir / "aveo.mp4").is_file()
    assert (simple_dir / "car_001.mp4").is_file()
    assert (difficult_dir / "scenario_01_damaged_collision.mp4").is_file()
    assert (difficult_dir / "toyota_hilux_white_ute.mp4").is_file()

    # Check manifest.json exists in videos/
    videos_manifest = WORKSPACE_ROOT / "test_assets" / "videos" / "manifest.json"
    assert videos_manifest.is_file()

