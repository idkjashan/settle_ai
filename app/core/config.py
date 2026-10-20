from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    
    # Postgres
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "settleai"
    POSTGRES_PASSWORD: str = "settleai_password"
    POSTGRES_DB: str = "settleai_db"
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    
    @property
    def REDIS_URL(self) -> str:
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # Storage (Local scratch & S3/MinIO)
    SCRATCH_DIR: str = "/tmp/autosettle_ingest"
    KEYFRAMES_DIR: str = "/tmp/autosettle_keyframes"
    STORAGE_DIR: str = "/tmp/autosettle_storage"
    S3_ENDPOINT: str | None = None
    S3_BUCKET: str = "autosettle-claims"
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None
    S3_REGION: str = "us-east-1"
    
    # Fast-Fail Gate (Stage 0) Thresholds
    MAX_UPLOAD_SIZE_BYTES: int = 100 * 1024 * 1024  # 100 MB
    CHUNK_SIZE_BYTES: int = 64 * 1024               # 64 KB
    LOCK_TTL_SECONDS: int = 60
    
    MIN_RESOLUTION_WIDTH: int = 720
    MIN_RESOLUTION_HEIGHT: int = 720
    MIN_DURATION_SECONDS: float = 5.0
    MAX_DURATION_SECONDS: float = 60.0
    MIN_FRAMERATE_FPS: float = 15.0
    
    LUMINANCE_MIN_THRESHOLD: float = 45.0
    LUMINANCE_MAX_THRESHOLD: float = 235.0
    SHARPNESS_MIN_THRESHOLD: float = 80.0
    SAMPLE_NORMALIZED_TIMESTAMPS: List[float] = [0.10, 0.30, 0.50, 0.70, 0.90]
    
    # Non-linear editor tag blacklist
    EDITOR_TAG_BLACKLIST: List[str] = [
        "capcut", "inshot", "premiere", "davinci", "kinemaster",
        "filmora", "vn video", "ffmpeg-splice", "vivavideo", "powerdirector"
    ]
    EDITOR_TAG_WHITELIST: List[str] = [
        "lavf", "libx264", "libvpx", "chrome", "apple", "android"
    ]
    
    # Stage 1 Settings
    YOLO_VEHICLE_MODEL_PATH: str = "yolo11m-seg.pt"
    GEMINI_API_KEY: str | None = None
    MAX_STAGE1_LATENCY_MS: int = 1750
    STAGE1_VRAM_LIMIT_MB: int = 1536

settings = Settings()

