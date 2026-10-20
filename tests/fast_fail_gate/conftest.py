import os
import shutil
import subprocess
from pathlib import Path
from typing import AsyncGenerator
import cv2
import numpy as np
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.infrastructure.db.session import async_session_factory
from app.infrastructure.db.seed import seed_database
from app.infrastructure.cache.redis_manager import redis_manager


FFMPEG_BIN = shutil.which("ffmpeg") or "/home/jashan/.local/bin/ffmpeg"
FFPROBE_BIN = shutil.which("ffprobe") or "/home/jashan/.local/bin/ffprobe"


def _run_ffmpeg(cmd: list[str]) -> bool:
    env = dict(os.environ)
    env["PATH"] = f"/home/jashan/.local/bin:{env.get('PATH', '')}"
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        return True
    except Exception:
        return False


def _create_synthetic_video_cv2(
    path: Path, width: int, height: int, duration_sec: int, fps: int = 30, color_mode: str = "normal"
) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(path), fourcc, float(fps), (width, height))
    total_frames = int(duration_sec * fps)

    for i in range(total_frames):
        if color_mode == "dark":
            frame = np.full((height, width, 3), 20, dtype=np.uint8)
        elif color_mode == "blurry":
            frame = np.full((height, width, 3), 128, dtype=np.uint8)
        else:
            frame = np.full((height, width, 3), 120, dtype=np.uint8)
            cv2.rectangle(frame, (50, 50), (width - 50, height - 50), (255, 255, 255), 4)
            cv2.putText(frame, f"Frame {i}", (100, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            cv2.circle(frame, (width // 2, height // 2), 60, (0, 255, 0), -1)
        out.write(frame)
    out.release()


@pytest.fixture(scope="session")
def video_fixtures_dir(tmp_path_factory) -> Path:
    """
    Session-scoped fixture generating synthetic MP4 video clips dynamically using ffmpeg.
    Falls back to OpenCV VideoWriter if ffmpeg is unavailable.
    """
    out_dir = tmp_path_factory.mktemp("test_videos")
    has_ffmpeg = bool(shutil.which(FFMPEG_BIN) or os.path.exists(FFMPEG_BIN))

    # 1. Clean 720p 15s video (valid)
    clean_720p = out_dir / "clean_720p_15s.mp4"
    if not (has_ffmpeg and _run_ffmpeg([
        FFMPEG_BIN, "-y", "-f", "lavfi",
        "-i", "testsrc2=size=1280x720:rate=30:duration=15",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(clean_720p)
    ])):
        _create_synthetic_video_cv2(clean_720p, 1280, 720, 15)

    # 2. Clean 1080p 15s video (valid)
    clean_1080p = out_dir / "clean_1080p_15s.mp4"
    if not (has_ffmpeg and _run_ffmpeg([
        FFMPEG_BIN, "-y", "-f", "lavfi",
        "-i", "testsrc2=size=1920x1080:rate=30:duration=15",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(clean_1080p)
    ])):
        _create_synthetic_video_cv2(clean_1080p, 1920, 1080, 15)

    # 3. Short video (< 5s, e.g. 3s)
    short_3s = out_dir / "short_3s.mp4"
    if not (has_ffmpeg and _run_ffmpeg([
        FFMPEG_BIN, "-y", "-f", "lavfi",
        "-i", "testsrc2=size=1280x720:rate=30:duration=3",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(short_3s)
    ])):
        _create_synthetic_video_cv2(short_3s, 1280, 720, 3)

    # 4. Long video (> 60s, e.g. 65s)
    long_65s = out_dir / "long_65s.mp4"
    if not (has_ffmpeg and _run_ffmpeg([
        FFMPEG_BIN, "-y", "-f", "lavfi",
        "-i", "testsrc2=size=1280x720:rate=30:duration=65",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(long_65s)
    ])):
        _create_synthetic_video_cv2(long_65s, 1280, 720, 65)

    # 5. Low-res video (640x360)
    lowres_360p = out_dir / "lowres_360p.mp4"
    if not (has_ffmpeg and _run_ffmpeg([
        FFMPEG_BIN, "-y", "-f", "lavfi",
        "-i", "testsrc2=size=640x360:rate=30:duration=10",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(lowres_360p)
    ])):
        _create_synthetic_video_cv2(lowres_360p, 640, 360, 10)

    # 6. Dark video (mean Y < 45)
    dark_vid = out_dir / "dark_video.mp4"
    if not (has_ffmpeg and _run_ffmpeg([
        FFMPEG_BIN, "-y", "-f", "lavfi",
        "-i", "testsrc2=size=1280x720:rate=30:duration=10",
        "-vf", "eq=brightness=-0.8:contrast=0.3",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(dark_vid)
    ])):
        _create_synthetic_video_cv2(dark_vid, 1280, 720, 10, color_mode="dark")

    # 7. Blurry video (Laplacian variance < 80)
    blurry_vid = out_dir / "blurry_video.mp4"
    if not (has_ffmpeg and _run_ffmpeg([
        FFMPEG_BIN, "-y", "-f", "lavfi",
        "-i", "testsrc2=size=1280x720:rate=30:duration=10",
        "-vf", "gblur=sigma=30",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(blurry_vid)
    ])):
        _create_synthetic_video_cv2(blurry_vid, 1280, 720, 10, color_mode="blurry")

    # 8. Video with CapCut metadata tag
    capcut_vid = out_dir / "capcut_video.mp4"
    if not (has_ffmpeg and _run_ffmpeg([
        FFMPEG_BIN, "-y", "-f", "lavfi",
        "-i", "testsrc2=size=1280x720:rate=30:duration=10",
        "-metadata", "comment=CapCut v11.0",
        "-metadata", "title=CapCut Project",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(capcut_vid)
    ])):
        _create_synthetic_video_cv2(capcut_vid, 1280, 720, 10)

    # 9. Corrupted file (> 1024 bytes to pass minimum ingest check, broken container)
    corrupt_vid = out_dir / "corrupted_video.mp4"
    corrupt_vid.write_bytes(b"ftypmp42\x00\x00\x00\x00" + b"\xde\xad\xbe\xef" * 512)

    return out_dir


@pytest.fixture
def clean_720p_video(video_fixtures_dir: Path) -> Path:
    return video_fixtures_dir / "clean_720p_15s.mp4"


@pytest.fixture
def clean_1080p_video(video_fixtures_dir: Path) -> Path:
    return video_fixtures_dir / "clean_1080p_15s.mp4"


@pytest.fixture
def short_video(video_fixtures_dir: Path) -> Path:
    return video_fixtures_dir / "short_3s.mp4"


@pytest.fixture
def long_video(video_fixtures_dir: Path) -> Path:
    return video_fixtures_dir / "long_65s.mp4"


@pytest.fixture
def lowres_video(video_fixtures_dir: Path) -> Path:
    return video_fixtures_dir / "lowres_360p.mp4"


@pytest.fixture
def dark_video(video_fixtures_dir: Path) -> Path:
    return video_fixtures_dir / "dark_video.mp4"


@pytest.fixture
def blurry_video(video_fixtures_dir: Path) -> Path:
    return video_fixtures_dir / "blurry_video.mp4"


@pytest.fixture
def capcut_video(video_fixtures_dir: Path) -> Path:
    return video_fixtures_dir / "capcut_video.mp4"


@pytest.fixture
def corrupt_video(video_fixtures_dir: Path) -> Path:
    return video_fixtures_dir / "corrupted_video.mp4"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def initialize_test_database():
    """Ensure database tables and seeded policies exist once per session."""
    try:
        await seed_database()
    except Exception:
        pass


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async test client with automatic demo state reset before and after each test."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # Reset state before test to ensure zero pollution
        await client.post("/api/v1/demo/reset")
        yield client
        # Reset state after test
        await client.post("/api/v1/demo/reset")


@pytest_asyncio.fixture
async def db_session():
    """Provides a fresh AsyncSession for database inspection during tests."""
    async with async_session_factory() as session:
        yield session
