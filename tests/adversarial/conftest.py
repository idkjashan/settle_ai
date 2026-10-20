"""
tests/adversarial/conftest.py
Pathological Fixtures, Corrupt Containers, Degenerate Inputs, and Database Helpers.
"""
import sys
from pathlib import Path
WORKSPACE_ROOT = Path("/home/jashan/settleai")
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

import asyncio
import os
import shutil
import subprocess
import tempfile
import uuid
from typing import AsyncGenerator, List, Tuple
import cv2
import numpy as np
import pytest
import pytest_asyncio

from app.infrastructure.db.session import async_session_factory, engine
from app.infrastructure.cache.redis_manager import redis_manager, RedisManager
from app.infrastructure.db.models import Base, InsuredPolicy, Claim
from app.infrastructure.db.seed import seed_database
WHITE_CAR_PATH = WORKSPACE_ROOT / "test_assets" / "hyundai_venue_white.jpg"
FFMPEG_BIN = shutil.which("ffmpeg") or "/home/jashan/.local/bin/ffmpeg"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def ensure_db_seeded():
    """Ensure database schema and seed policies exist."""
    await seed_database()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator:
    """Provides an isolated AsyncSession connected to PostgreSQL."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()


@pytest_asyncio.fixture
async def redis_mgr() -> RedisManager:
    """Provides the live Redis manager instance."""
    return redis_manager


@pytest.fixture(scope="session")
def adv_assets_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("adversarial_assets")


@pytest.fixture(scope="session")
def truncated_zero_frame_video(adv_assets_dir) -> Path:
    """
    Creates an MP4 file with valid container header (moov atom at beginning)
    but truncated immediately before any video frames (mdat is cut off).
    cv2.VideoCapture.isOpened() returns True, but cap.read() immediately returns False.
    """
    full_path = adv_assets_dir / "temp_full.mp4"
    trunc_path = adv_assets_dir / "truncated_zero_frame.mp4"
    
    # 1 second valid mp4 with faststart so moov is at head
    cmd = [
        FFMPEG_BIN, "-y",
        "-f", "lavfi", "-i", "color=c=black:s=640x360:r=30",
        "-t", "1",
        "-movflags", "faststart",
        str(full_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Take first 1500 bytes: includes ftyp and moov, but no readable video frame packets
    data = full_path.read_bytes()
    trunc_path.write_bytes(data[:1500])
    
    # Verify properties
    cap = cv2.VideoCapture(str(trunc_path))
    opened = cap.isOpened()
    ret, frame = cap.read()
    cap.release()
    assert opened is True, "Expected cap.isOpened() to be True"
    assert ret is False, "Expected cap.read() to return False (0 frames)"
    return trunc_path


@pytest.fixture(scope="session")
def audio_only_mp4(adv_assets_dir) -> Path:
    """Generates an audio-only MP4 file (AAC stream, no video stream)."""
    out_path = adv_assets_dir / "audio_only.mp4"
    cmd = [
        FFMPEG_BIN, "-y",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "5",
        "-c:a", "aac",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_path


@pytest.fixture(scope="session")
def low_framerate_video(adv_assets_dir) -> Path:
    """Generates an MP4 video at 10 fps (below the 15 fps minimum threshold)."""
    out_path = adv_assets_dir / "low_fps_10.mp4"
    cmd = [
        FFMPEG_BIN, "-y",
        "-f", "lavfi", "-i", "color=c=gray:s=1280x720:r=10",
        "-t", "6",
        "-c:v", "libx264",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out_path


@pytest.fixture(scope="session")
def overexposed_textured_video(adv_assets_dir) -> Path:
    """
    Generates a 6-second 1280x720 video with severe overexposure / wash-out (mean luminance ~223-228).
    Includes high-frequency noise so Laplacian sharpness > 80 (not blurry), isolating luminance gate.
    """
    out_path = adv_assets_dir / "overexposed_textured.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(str(out_path), fourcc, 30.0, (1280, 720))
    for _ in range(180):
        # Pixel values in 215-240 give mean luminance ~225, with strong Laplacian edges
        noise = np.random.randint(212, 240, (720, 1280, 3), dtype=np.uint8)
        vw.write(noise)
    vw.release()
    return out_path


@pytest.fixture(scope="session")
def truncated_15s_quorum_attack_video(adv_assets_dir) -> Path:
    """
    Generates an MP4 whose container metadata claims 15.0 seconds duration,
    but is truncated such that only the first sample (frame ~45 at 10% pos) can be read,
    and all remaining frames (at 30%, 50%, 70%, 90%) are missing.
    """
    full = adv_assets_dir / "full_15s.mp4"
    trunc = adv_assets_dir / "trunc_15s_quorum.mp4"
    cmd = [
        FFMPEG_BIN, "-y",
        "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30",
        "-t", "15",
        "-c:v", "libx264",
        "-movflags", "faststart",
        str(full),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    data = full.read_bytes()
    # 25% of file size keeps moov and ~50 frames (enough for sample at 10% = frame 45, but cuts off the rest)
    trunc.write_bytes(data[:len(data) // 4])
    return trunc
