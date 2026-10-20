import shutil
import uuid
from pathlib import Path
from typing import Optional
from app.core.config import settings
from app.core.logging import logger

class S3Client:
    """
    Storage client that stores artifacts either to MinIO / AWS S3 or to local storage directory.
    Seamlessly falls back to local storage when S3 endpoint is not configured.
    """
    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        bucket_name: Optional[str] = None,
        storage_dir: Optional[str] = None,
    ):
        self.endpoint_url = endpoint_url or settings.S3_ENDPOINT
        self.bucket_name = bucket_name or settings.S3_BUCKET
        self.storage_dir = Path(storage_dir or settings.STORAGE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    async def upload_file(self, local_path: Path, s3_key: str) -> str:
        """
        Uploads local file to persistent storage key: claims/{claim_id}/raw/walkaround.mp4.
        Returns the resolved storage key.
        """
        if not local_path.exists():
            raise FileNotFoundError(f"Local file {local_path} does not exist.")

        if self.endpoint_url:
            # S3 / MinIO upload path using aioboto3 if configured
            try:
                import aioboto3
                session = aioboto3.Session()
                async with session.client(
                    "s3",
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=settings.S3_ACCESS_KEY,
                    aws_secret_access_key=settings.S3_SECRET_KEY,
                    region_name=settings.S3_REGION,
                ) as s3:
                    with open(local_path, "rb") as f:
                        await s3.upload_fileobj(f, self.bucket_name, s3_key)
                    logger.info(f"Uploaded {local_path} to s3://{self.bucket_name}/{s3_key}")
                    return f"s3://{self.bucket_name}/{s3_key}"
            except Exception as e:
                logger.warning(f"S3 upload failed ({e}), falling back to local persistent storage.")

        # Local fallback persistence
        dest_path = self.storage_dir / s3_key
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest_path)
        logger.info(f"Persisted {local_path} to local storage at {dest_path}")
        return str(dest_path)

    async def delete_file(self, s3_key: str) -> bool:
        dest_path = self.storage_dir / s3_key
        if dest_path.exists():
            dest_path.unlink()
            return True
        return False

s3_client = S3Client()

