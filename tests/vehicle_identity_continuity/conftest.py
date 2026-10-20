import os
_ffmpeg_dir = r"C:\Users\Hp\AppData\Local\ffmpeg\bin"
if os.path.exists(_ffmpeg_dir) and _ffmpeg_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{_ffmpeg_dir};{os.environ.get('PATH', '')}"

"""
tests/vehicle_identity_continuity/conftest.py
Deterministic Synthetic Clip Factory & Shared Pytest Fixtures for Stage 1.
"""
import asyncio
import os
import subprocess
import uuid
from pathlib import Path
from typing import AsyncGenerator, List, Tuple
import cv2
import numpy as np
import pytest
import pytest_asyncio

from app.infrastructure.db.session import async_session_factory, engine
from app.infrastructure.cache.redis_manager import redis_manager, RedisManager
from app.infrastructure.db.models import Claim, InsuredPolicy

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
WHITE_CAR_PATH = WORKSPACE_ROOT / "test_assets" / "hyundai_venue_white.jpg"
BLUE_CAR_PATH = WORKSPACE_ROOT / "test_assets" / "hyundai_venue_blue.jpg"
FFMPEG_BIN = "ffmpeg"


def encode_frames_to_mp4(frames: List[np.ndarray], output_path: Path, fps: float = 30.0) -> Path:
    """Encodes list of BGR numpy frames to a valid H.264/yuv420p MP4 container."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not frames:
        raise ValueError("Frames list cannot be empty")

    h, w = frames[0].shape[:2]
    # Ensure dimensions are even for libx264
    w = w if w % 2 == 0 else w - 1
    h = h if h % 2 == 0 else h - 1

    ffmpeg_path = FFMPEG_BIN if os.path.exists(FFMPEG_BIN) else "ffmpeg"
    cmd = [
        ffmpeg_path,
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{w}x{h}",
        "-pix_fmt", "bgr24",
        "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "veryfast",
        str(output_path),
    ]

    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        for frame in frames:
            crop = frame[:h, :w]
            proc.stdin.write(crop.tobytes())
        proc.stdin.close()
        proc.wait()
    except Exception:
        # Fallback to OpenCV VideoWriter
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(output_path), fourcc, fps, (w, h))
        for f in frames:
            out.write(f[:h, :w])
        out.release()

    return output_path


def overlay_plate_on_car(
    base_frame: np.ndarray,
    plate_text: str,
    x: int = 510,
    y: int = 430,
    w: int = 260,
    h: int = 60,
    two_line: bool = False,
) -> np.ndarray:
    """Overlays a clean, high-contrast license plate onto the bumper area of the vehicle."""
    img = base_frame.copy()

    if two_line:
        # 2-line stacked Indian HSRP plate: e.g. "MH 12" over "DE 1433"
        px = 540 if x == 510 else x
        py = 410 if y == 430 else y
        pw = 200
        ph = 95
        cv2.rectangle(img, (px, py), (px + pw, py + ph), (255, 255, 255), -1)
        cv2.rectangle(img, (px, py), (px + pw, py + ph), (10, 10, 10), 3)
        cv2.putText(
            img, "MH 12", (px + 25, py + 38),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (10, 10, 10), 2, cv2.LINE_AA
        )
        cv2.putText(
            img, "DE 1433", (px + 10, py + 80),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (10, 10, 10), 2, cv2.LINE_AA
        )
    else:
        # Draw white plate background with black border
        cv2.rectangle(img, (x, y), (x + w, y + h), (255, 255, 255), -1)
        cv2.rectangle(img, (x, y), (x + w, y + h), (10, 10, 10), 3)
        cv2.putText(
            img, plate_text, (x + 14, y + 42),
            cv2.FONT_HERSHEY_SIMPLEX, 0.95, (10, 10, 10), 2, cv2.LINE_AA
        )
    return img


@pytest.fixture(scope="session")
def clips_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("stage1_benchmark_clips")


@pytest.fixture(scope="session")
def base_white_image() -> np.ndarray:
    assert WHITE_CAR_PATH.exists(), f"Missing {WHITE_CAR_PATH}"
    img = cv2.imread(str(WHITE_CAR_PATH))
    assert img is not None, "Failed to read white car asset"
    return cv2.resize(img, (1280, 720))


@pytest.fixture(scope="session")
def base_blue_image() -> np.ndarray:
    assert BLUE_CAR_PATH.exists(), f"Missing {BLUE_CAR_PATH}"
    img = cv2.imread(str(BLUE_CAR_PATH))
    assert img is not None, "Failed to read blue car asset"
    return cv2.resize(img, (1280, 720))


# ---------------------------------------------------------------------------
# Synthetic Benchmark Clip Fixtures (T1-01 through T1-14)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def clip_happy_creta_white(clips_dir, base_white_image) -> Path:
    """T1-01: Clean continuous walkaround with single-line plate MH 12 DE 1433 on White Creta."""
    out_path = clips_dir / "clip_happy_creta_white.mp4"
    if out_path.exists():
        return out_path

    plate_img = overlay_plate_on_car(base_white_image, "MH 12 DE 1433")
    frames = []
    # 60 frames (2.0s) with continuous gentle camera drift
    h, w = plate_img.shape[:2]
    for i in range(60):
        dx = int(i * 0.8)
        M = np.float32([[1, 0, dx], [0, 1, 0]])
        frame = cv2.warpAffine(plate_img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
        frames.append(frame)

    return encode_frames_to_mp4(frames, out_path, 30.0)


@pytest.fixture(scope="session")
def clip_2line_rear_plate(clips_dir, base_white_image) -> Path:
    """T1-02: White Creta with 2-line stacked Indian HSRP rear plate (MH 12 over DE 1433)."""
    out_path = clips_dir / "clip_2line_rear_plate.mp4"
    if out_path.exists():
        return out_path

    plate_img = overlay_plate_on_car(
        base_white_image, "MH 12 DE 1433", two_line=True
    )
    frames = []
    h, w = plate_img.shape[:2]
    for i in range(45):
        dx = int(i * 0.5)
        M = np.float32([[1, 0, dx], [0, 1, 0]])
        frame = cv2.warpAffine(plate_img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
        frames.append(frame)

    return encode_frames_to_mp4(frames, out_path, 30.0)


@pytest.fixture(scope="session")
def clip_homoglyph_plate(clips_dir, base_white_image) -> Path:
    """T1-03: Plate reading MH 12 0E 1433 (optical homoglyph 0 vs D)."""
    out_path = clips_dir / "clip_homoglyph_plate.mp4"
    if out_path.exists():
        return out_path

    plate_img = overlay_plate_on_car(base_white_image, "MH 12 0E 1433")
    frames = []
    h, w = plate_img.shape[:2]
    for i in range(45):
        dx = int(i * 0.5)
        M = np.float32([[1, 0, dx], [0, 1, 0]])
        frame = cv2.warpAffine(plate_img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
        frames.append(frame)

    return encode_frames_to_mp4(frames, out_path, 30.0)


@pytest.fixture(scope="session")
def clip_macro_closeup(clips_dir, base_white_image) -> Path:
    """T1-06: Macro close-up camera zoom into panel (area ratio > 0.50)."""
    out_path = clips_dir / "clip_macro_closeup.mp4"
    if out_path.exists():
        return out_path

    plate_img = overlay_plate_on_car(base_white_image, "MH 12 DE 1433")
    frames = []
    h, w = plate_img.shape[:2]
    # Zoom from scale 1.0 to 3.0 into center door panel
    for i in range(60):
        scale = 1.0 + (i / 59.0) * 2.0
        nw, nh = int(w / scale), int(h / scale)
        x1 = int(w * 0.45 - nw * 0.5)
        y1 = int(h * 0.50 - nh * 0.5)
        crop = plate_img[max(0, y1):min(h, y1 + nh), max(0, x1):min(w, x1 + nw)]
        zoomed = cv2.resize(crop, (w, h))
        frames.append(zoomed)

    return encode_frames_to_mp4(frames, out_path, 30.0)


@pytest.fixture(scope="session")
def clip_spliced_cut(clips_dir, base_white_image) -> Path:
    """T1-07: Hard cut splice at frame 30 between car walkaround and unrelated red scene."""
    out_path = clips_dir / "clip_spliced_cut.mp4"
    if out_path.exists():
        return out_path

    plate_img = overlay_plate_on_car(base_white_image, "MH 12 DE 1433")
    h, w = plate_img.shape[:2]
    frames = []
    # First 30 frames: white car with motion
    for i in range(30):
        dx = int(i * 0.8)
        M = np.float32([[1, 0, dx], [0, 1, 0]])
        frames.append(cv2.warpAffine(plate_img, M, (w, h), borderMode=cv2.BORDER_REFLECT))
    # Next 30 frames: solid red scene with motion
    for i in range(30):
        red_scene = np.full_like(plate_img, (20, 20, 180 + (i % 20)))
        frames.append(red_scene)

    return encode_frames_to_mp4(frames, out_path, 30.0)


@pytest.fixture(scope="session")
def clip_same_car_jump_splice(clips_dir, base_white_image) -> Path:
    """T1-08: Subtle jump-cut splice of the same white car (triggers grid SSIM drop)."""
    out_path = clips_dir / "clip_same_car_jump_splice.mp4"
    if out_path.exists():
        return out_path

    plate_img = overlay_plate_on_car(base_white_image, "MH 12 DE 1433")
    h, w = plate_img.shape[:2]
    frames = []
    # First 30 frames: normal with motion
    for i in range(30):
        dx = int(i * 0.8)
        M = np.float32([[1, 0, dx], [0, 1, 0]])
        frames.append(cv2.warpAffine(plate_img, M, (w, h), borderMode=cv2.BORDER_REFLECT))
    # Next 30 frames: abrupt flip + motion
    jump_frame = cv2.flip(plate_img, 1)
    for i in range(30):
        dx = int(i * 0.8)
        M = np.float32([[1, 0, dx], [0, 1, 0]])
        frames.append(cv2.warpAffine(jump_frame, M, (w, h), borderMode=cv2.BORDER_REFLECT))

    return encode_frames_to_mp4(frames, out_path, 30.0)


@pytest.fixture(scope="session")
def clip_freeze_frame_24(clips_dir, base_white_image) -> Path:
    """T1-09: Freeze frame running for 24 identical consecutive frames (> 15 max allowed)."""
    out_path = clips_dir / "clip_freeze_frame_24.mp4"
    if out_path.exists():
        return out_path

    plate_img = overlay_plate_on_car(base_white_image, "MH 12 DE 1433")
    h, w = plate_img.shape[:2]
    frames = []
    # Frames 0..17: gentle camera motion
    for i in range(18):
        M = np.float32([[1, 0, i], [0, 1, 0]])
        frames.append(cv2.warpAffine(plate_img, M, (w, h), borderMode=cv2.BORDER_REFLECT))
    # Frames 18..42: EXACT duplicate frozen frame for 25 frames
    frozen = frames[-1].copy()
    for _ in range(25):
        frames.append(frozen.copy())
    # Frames 43..59: motion resumes
    for i in range(17):
        M = np.float32([[1, 0, 18 + i], [0, 1, 0]])
        frames.append(cv2.warpAffine(plate_img, M, (w, h), borderMode=cv2.BORDER_REFLECT))

    return encode_frames_to_mp4(frames, out_path, 30.0)


@pytest.fixture(scope="session")
def clip_wrong_plate(clips_dir, base_white_image) -> Path:
    """T1-10: Legible plate DL 09 CA 8821 on White Creta (mismatched policy)."""
    out_path = clips_dir / "clip_wrong_plate.mp4"
    if out_path.exists():
        return out_path

    plate_img = overlay_plate_on_car(base_white_image, "DL 09 CA 8821")
    frames = []
    h, w = plate_img.shape[:2]
    for i in range(45):
        dx = int(i * 0.5)
        M = np.float32([[1, 0, dx], [0, 1, 0]])
        frame = cv2.warpAffine(plate_img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
        frames.append(frame)

    return encode_frames_to_mp4(frames, out_path, 30.0)


@pytest.fixture(scope="session")
def clip_blue_car_spoof_plate(clips_dir, base_blue_image) -> Path:
    """T1-11: Blue car bearing legitimate plate MH 12 DE 1433 (violates WHITE policy)."""
    out_path = clips_dir / "clip_blue_car_spoof_plate.mp4"
    if out_path.exists():
        return out_path

    plate_img = overlay_plate_on_car(base_blue_image, "MH 12 DE 1433")
    frames = []
    h, w = plate_img.shape[:2]
    for i in range(45):
        dx = int(i * 0.5)
        M = np.float32([[1, 0, dx], [0, 1, 0]])
        frame = cv2.warpAffine(plate_img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
        frames.append(frame)

    return encode_frames_to_mp4(frames, out_path, 30.0)


@pytest.fixture(scope="session")
def clip_track_lost_30frames(clips_dir, base_white_image) -> Path:
    """T1-13: Camera pans to floor for 36 frames (> 15 threshold in wide view)."""
    out_path = clips_dir / "clip_track_lost_30frames.mp4"
    if out_path.exists():
        return out_path

    plate_img = overlay_plate_on_car(base_white_image, "MH 12 DE 1433")
    h, w = plate_img.shape[:2]
    asphalt_floor = np.full_like(plate_img, (60, 60, 60))
    frames = []
    # Frames 0..19: Car visible
    for _ in range(20):
        frames.append(plate_img.copy())
    # Frames 20..59 (40 frames): Points at floor (no car)
    for _ in range(40):
        frames.append(asphalt_floor.copy())
    # Frames 60..74: Car returns
    for _ in range(15):
        frames.append(plate_img.copy())

    return encode_frames_to_mp4(frames, out_path, 30.0)


@pytest.fixture(scope="session")
def clip_parking_lot_switch(clips_dir, base_white_image) -> Path:
    """T1-14: Starts on Car 1, pans to adjacent parked Car 2 (different track ID)."""
    out_path = clips_dir / "clip_parking_lot_switch.mp4"
    if out_path.exists():
        return out_path

    plate_img = overlay_plate_on_car(base_white_image, "MH 12 DE 1433")
    h, w = plate_img.shape[:2]
    frames = []
    # Car 1 on left side for frames 0..24
    for i in range(25):
        frame = np.full_like(plate_img, (50, 50, 50))
        small = cv2.resize(plate_img, (int(w * 0.55), int(h * 0.55)))
        sh, sw = small.shape[:2]
        frame[h - sh - 50:h - 50, 40:40 + sw] = small
        frames.append(frame)
    # Transition / pan to Car 2 on right side for frames 25..59
    for i in range(35):
        frame = np.full_like(plate_img, (50, 50, 50))
        car2 = cv2.flip(plate_img, 1)
        small2 = cv2.resize(car2, (int(w * 0.55), int(h * 0.55)))
        sh2, sw2 = small2.shape[:2]
        frame[h - sh2 - 50:h - 50, w - sw2 - 40:w - 40] = small2
        frames.append(frame)

    return encode_frames_to_mp4(frames, out_path, 30.0)


# ---------------------------------------------------------------------------
# Database & Redis Fixtures
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock
from tests.in_memory_db import patch_in_memory_db, in_memory_db

patch_in_memory_db()

@pytest_asyncio.fixture
async def db_session():
    yield AsyncMock()

@pytest_asyncio.fixture
async def redis_mgr() -> RedisManager:
    """Provides the live Redis manager instance."""
    return redis_manager


@pytest_asyncio.fixture(autouse=True)
async def reset_test_state():
    in_memory_db.reset()
