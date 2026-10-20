import os
import hashlib
import uuid
from pathlib import Path
from typing import Optional
from fastapi import UploadFile
from app.core.config import settings
from app.core.exceptions import PayloadTooLargeException, AutoSettleException
from app.core.logging import logger

class ScratchFileLease:
    """
    RAII resource lease managing the lifecycle of the local scratch video file.
    If not explicitly transferred to downstream processing, calling cleanup() unlinks the file.
    """
    def __init__(self, claim_id: uuid.UUID, file_path: Path, sha256_hex: str, file_size_bytes: int):
        self.claim_id = claim_id
        self.file_path = file_path
        self.sha256_hex = sha256_hex
        self.file_size_bytes = file_size_bytes
        self.transferred_to_downstream: bool = False

    def transfer_to_downstream(self) -> Path:
        """Transfers ownership of the scratch file to Stage 1, preventing deletion on fast-fail cleanup."""
        self.transferred_to_downstream = True
        return self.file_path

    def cleanup(self) -> None:
        """Unlinks the scratch file from disk if not transferred to downstream."""
        if not self.transferred_to_downstream:
            try:
                if self.file_path.exists():
                    self.file_path.unlink()
                    logger.debug(f"Unlinked scratch file {self.file_path} for claim {self.claim_id}")
            except Exception as e:
                logger.warning(f"Failed to unlink scratch file {self.file_path}: {e}")


class ScratchIngestService:
    def __init__(
        self,
        scratch_dir: Optional[str] = None,
        max_bytes: Optional[int] = None,
        chunk_size: Optional[int] = None,
    ):
        self.scratch_dir = Path(scratch_dir or settings.SCRATCH_DIR)
        self.max_bytes = max_bytes or settings.MAX_UPLOAD_SIZE_BYTES
        self.chunk_size = chunk_size or settings.CHUNK_SIZE_BYTES
        self.scratch_dir.mkdir(parents=True, exist_ok=True)

    async def stream_to_scratch(self, claim_id: uuid.UUID, upload_file: UploadFile) -> ScratchFileLease:
        """
        Streams uploaded multipart file in bounded 64KB chunks to /tmp/autosettle_ingest/{claim_id}.mp4.
        Computes SHA-256 on the fly and enforces the 100MB size ceiling.
        """
        target_path = self.scratch_dir / f"{claim_id}.mp4"
        sha256 = hashlib.sha256()
        total_bytes = 0

        try:
            with open(target_path, "wb") as f:
                while True:
                    chunk = await upload_file.read(self.chunk_size)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > self.max_bytes:
                        raise PayloadTooLargeException(
                            f"File size exceeds maximum allowed {self.max_bytes // (1024 * 1024)} MB."
                        )
                    sha256.update(chunk)
                    f.write(chunk)

            if total_bytes < 1024:
                # File is essentially empty or corrupted (< 1 KB)
                if target_path.exists():
                    target_path.unlink()
                raise AutoSettleException(
                    "Uploaded file is corrupt or empty (size < 1 KB).",
                    code="FILE_CORRUPT_OR_EMPTY",
                )

            return ScratchFileLease(
                claim_id=claim_id,
                file_path=target_path,
                sha256_hex=sha256.hexdigest(),
                file_size_bytes=total_bytes,
            )

        except Exception:
            if target_path.exists():
                try:
                    target_path.unlink()
                except Exception:
                    pass
            raise

scratch_ingest_service = ScratchIngestService()

