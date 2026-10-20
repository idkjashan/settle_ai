import os
from pathlib import Path
from typing import Dict, Tuple, Optional
import cv2
import numpy as np
from app.domain.vehicle_identity_continuity.config import stage1_settings
from app.core.logging import logger

class KeyframeSelector:
    """
    Gate 3B: Inline Rolling Top-K Keyframe Selector.
    Scores sharpness and specular glare, maintaining best candidates and saving them atomically.
    """
    def __init__(self):
        self.settings = stage1_settings

    def score_frame(self, frame_bgr: np.ndarray) -> Tuple[float, float, float]:
        """
        Returns (sharpness, glare_ratio, combined_quality_score).
        """
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        v = hsv[:, :, 2]
        glare_pixels = np.sum(v >= self.settings.GLARE_THRESHOLD_V)
        glare_ratio = float(glare_pixels / v.size)

        score = sharpness * max(0.1, 1.0 - (self.settings.GLARE_PENALTY_WEIGHT * glare_ratio))
        return sharpness, glare_ratio, score

    def save_keyframe_atomically(
        self, frame_bgr: np.ndarray, claim_id: str, canonical_part_key: str
    ) -> Path:
        output_dir = Path(self.settings.KEYFRAME_OUTPUT_DIR) / str(claim_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        final_path = output_dir / f"{canonical_part_key}.jpg"
        tmp_path = output_dir / f"{canonical_part_key}.tmp.jpg"

        cv2.imwrite(str(tmp_path), frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        os.replace(str(tmp_path), str(final_path))
        logger.info(f"Saved keyframe atomically: {final_path}")
        return final_path

keyframe_selector = KeyframeSelector()

