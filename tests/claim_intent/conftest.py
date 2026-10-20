"""
tests/claim_intent/conftest.py
Hermetic test fixtures and in-memory mock environment for Claim Intent & Stage 2 testing.
"""
from pathlib import Path
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.infrastructure.db.session import get_db_session
from tests.in_memory_db import patch_in_memory_db

# Patch in-memory database & redis mock
patch_in_memory_db()


async def override_get_db_session():
    yield None


app.dependency_overrides[get_db_session] = override_get_db_session


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


import shutil
import subprocess

FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"


@pytest.fixture
def dummy_video_file(tmp_path: Path) -> Path:
    """Creates a temporary valid dummy mp4 container for API upload testing."""
    video_path = tmp_path / "test_walkaround.mp4"
    # Generate a lightweight 6s 720p synthetic mp4
    cmd = [
        FFMPEG_BIN, "-y", "-f", "lavfi",
        "-i", "testsrc2=size=1280x720:rate=30:duration=6",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(video_path),
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        ftyp = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free"
        video_path.write_bytes(ftyp + b"\x00" * 4096)
    return video_path
