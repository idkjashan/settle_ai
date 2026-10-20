import os
import hashlib
import uuid
from pathlib import Path
from typing import Optional, List
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


class ScratchPhotoPackLease:
    """
    RAII resource lease managing the lifecycle of uploaded photo pack scratch files.
    """
    def __init__(self, claim_id: uuid.UUID, file_paths: List[Path], sha256_hex: str, file_size_bytes: int):
        self.claim_id = claim_id
        self.file_paths = file_paths
        self.sha256_hex = sha256_hex
        self.file_size_bytes = file_size_bytes
        self.transferred_to_downstream: bool = False

    def transfer_to_downstream(self) -> List[Path]:
        self.transferred_to_downstream = True
        return self.file_paths

    def cleanup(self) -> None:
        if not self.transferred_to_downstream:
            for p in self.file_paths:
                try:
                    if p.exists():
                        p.unlink()
                except Exception as e:
                    logger.warning(f"Failed to unlink scratch photo {p}: {e}")
            # Try removing directory if empty
            if self.file_paths:
                parent = self.file_paths[0].parent
                if parent.exists() and parent != Path(settings.SCRATCH_DIR):
                    try:
                        parent.rmdir()
                    except Exception:
                        pass


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

    async def stream_photo_pack_to_scratch(
        self, claim_id: uuid.UUID, upload_files: List[UploadFile]
    ) -> ScratchPhotoPackLease:
        """
        Streams uploaded photo files to /tmp/autosettle_ingest/{claim_id}/photo_{idx}_{name}.
        Computes cumulative SHA-256 and enforces total size limits.
        """
        claim_folder = self.scratch_dir / str(claim_id)
        claim_folder.mkdir(parents=True, exist_ok=True)
        file_paths: List[Path] = []
        overall_hasher = hashlib.sha256()
        total_bytes = 0

        try:
            for idx, uf in enumerate(upload_files):
                filename = uf.filename or f"photo_{idx}.jpg"
                clean_name = f"photo_{idx}_{Path(filename).name}"
                target_path = claim_folder / clean_name
                file_paths.append(target_path)
                file_hasher = hashlib.sha256()

                with open(target_path, "wb") as f:
                    while True:
                        chunk = await uf.read(self.chunk_size)
                        if not chunk:
                            break
                        total_bytes += len(chunk)
                        if total_bytes > self.max_bytes:
                            raise PayloadTooLargeException(
                                f"Total photo pack size exceeds maximum allowed {self.max_bytes // (1024 * 1024)} MB."
                            )
                        file_hasher.update(chunk)
                        f.write(chunk)

                overall_hasher.update(file_hasher.digest())

            return ScratchPhotoPackLease(
                claim_id=claim_id,
                file_paths=file_paths,
                sha256_hex=overall_hasher.hexdigest(),
                file_size_bytes=total_bytes,
            )

        except Exception:
            for p in file_paths:
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass
            if claim_folder.exists():
                try:
                    claim_folder.rmdir()
                except Exception:
                    pass
            raise

scratch_ingest_service = ScratchIngestService()

