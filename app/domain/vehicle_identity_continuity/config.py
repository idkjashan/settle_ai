from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Tuple

class Stage1Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Gate 1: CPU Cut & Splice Detector
    DOWNSAMPLE_WIDTH: int = 320
    DOWNSAMPLE_HEIGHT: int = 180
    PYSCENEDETECT_THRESHOLD: float = 27.0
    MIN_GLOBAL_HSV_CORR: float = 0.60
    MIN_GRID_P25_HSV_CORR: float = 0.52
    MIN_TRIGGERED_SSIM: float = 0.68
    MAX_FROZEN_FRAMES: int = 15

    # Gate 2: Progressive ANPR & Color Match
    INITIAL_WINDOW_SECONDS: float = 3.5
    MIN_VEHICLE_AREA_RATIO: float = 0.12
    BUMPER_Y_REL_MIN: float = 0.28
    BUMPER_Y_REL_MAX: float = 0.96
    MAX_HOMOGLYPH_EDIT_COST: float = 2.0
    MIN_OCR_CONFIDENCE_AUTO_ACCEPT: float = 0.85
    MAX_HSV_COLOR_DELTA: float = 35.0

    # 2-Line HSRP Plate Merging
    HSRP_MIN_HORIZONTAL_OVERLAP: float = 0.35
    HSRP_MAX_VERTICAL_GAP_RATIO: float = 1.8

    # Gate 3: Reset-Safe Strided ByteTrack & Keyframes
    VID_STRIDE: int = 3
    CLOSEUP_ZOOM_AREA_RATIO: float = 0.50
    MAX_WIDE_TRACK_LOST_FRAMES: int = 15
    SHARPNESS_MIN_FOR_KEYFRAME: float = 80.0
    GLARE_THRESHOLD_V: int = 245
    GLARE_PENALTY_WEIGHT: float = 0.40

    # Model & Runtime
    YOLO_MODEL_PATH: str = "weights/yolo11m-seg.pt"
    KEYFRAME_OUTPUT_DIR: str = "/tmp/autosettle_keyframes"
    STAGE1_TIMEOUT_MS: int = 1750

stage1_settings = Stage1Settings()

