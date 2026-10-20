import math
import time
from typing import Optional, Dict, Any, Tuple
import cv2
import numpy as np
from app.domain.vehicle_identity_continuity.config import stage1_settings
from app.domain.vehicle_identity_continuity.schemas import ColorValidationResult, PolicyGroundingContext
from app.core.logging import logger

STANDARD_COLOR_BOUNDS = {
    "WHITE": {"type": "achromatic", "s_max": 65, "v_min": 85, "v_max": 255},
    "BLACK": {"type": "achromatic", "s_max": 45, "v_max": 100},
    "SILVER": {"type": "achromatic", "s_max": 55, "v_min": 90, "v_max": 220},
    "GREY": {"type": "achromatic", "s_max": 55, "v_min": 60, "v_max": 180},
    "GRAY": {"type": "achromatic", "s_max": 55, "v_min": 60, "v_max": 180},
    "RED": {"type": "chromatic", "target_h": 5, "s_min": 80, "v_min": 70},
    "BLUE": {"type": "chromatic", "target_h": 115, "s_min": 55, "v_min": 60},
    "GREEN": {"type": "chromatic", "target_h": 60, "s_min": 70, "v_min": 60},
    "YELLOW": {"type": "chromatic", "target_h": 25, "s_min": 100, "v_min": 120},
    "ORANGE": {"type": "chromatic", "target_h": 15, "s_min": 100, "v_min": 100},
    "BROWN": {"type": "chromatic", "target_h": 15, "s_min": 30, "v_min": 30},
}

CANONICAL_COLOR_KEYWORDS = (
    "WHITE", "BLACK", "SILVER", "GREY", "GRAY",
    "RED", "BLUE", "GREEN", "YELLOW", "ORANGE", "BROWN"
)

def extract_canonical_color_keyword(raw_color: str) -> str:
    """
    Extract canonical color keyword from multi-word or composite automotive color name.
    # ponytail: Token matching handles composite automotive names (e.g. 'Metallic Blue' -> 'BLUE')
    """
    norm = raw_color.upper().replace("-", " ").replace("_", " ")
    tokens = norm.split()
    for kw in CANONICAL_COLOR_KEYWORDS:
        if kw in tokens:
            return kw
    for kw in CANONICAL_COLOR_KEYWORDS:
        if kw in norm:
            return kw
    return norm

class ColorGroundingValidator:
    def __init__(self):
        self.settings = stage1_settings

    def validate_paint_color(
        self,
        frame_bgr: np.ndarray,
        vehicle_bbox: Optional[Tuple[int, int, int, int]],
        grounding_context: PolicyGroundingContext,
    ) -> ColorValidationResult:
        t0 = time.perf_counter()
        raw_color = grounding_context.registered_color.upper()
        expected_color_name = extract_canonical_color_keyword(raw_color)

        if frame_bgr is None or vehicle_bbox is None:
            return ColorValidationResult(
                is_color_match=False,
                expected_color_name=expected_color_name,
                failure_code="ESC-01",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        x1, y1, x2, y2 = vehicle_bbox
        h_f, w_f = frame_bgr.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w_f, x2), min(h_f, y2)

        # ponytail: guard against degenerate/inverted bounding boxes
        if x2 <= x1 or y2 <= y1:
            return ColorValidationResult(
                is_color_match=False,
                expected_color_name=expected_color_name,
                failure_code="ESC-01",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        # Crop vehicle center panel (ignore top 20% for windshield/sky and bottom 15% for tires)
        vh = y2 - y1
        vw = x2 - x1
        crop_y1 = int(y1 + vh * 0.20)
        crop_y2 = int(y1 + vh * 0.85)
        crop_x1 = int(x1 + vw * 0.15)
        crop_x2 = int(x1 + vw * 0.85)

        if crop_x2 <= crop_x1 or crop_y2 <= crop_y1:
            veh_crop = frame_bgr[y1:y2, x1:x2]
        else:
            veh_crop = frame_bgr[crop_y1:crop_y2, crop_x1:crop_x2]

        if veh_crop.size == 0:
            veh_crop = frame_bgr[y1:y2, x1:x2]

        if veh_crop.size == 0:
            return ColorValidationResult(
                is_color_match=False,
                expected_color_name=expected_color_name,
                failure_code="ESC-01",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        hsv = cv2.cvtColor(veh_crop, cv2.COLOR_BGR2HSV)
        h_channel = hsv[:, :, 0].flatten()
        s_channel = hsv[:, :, 1].flatten()
        v_channel = hsv[:, :, 2].flatten()

        # Paint filter: exclude deep shadows (V < 40) and specular glare (V > 250, S < 25)
        valid_mask = (v_channel >= 40) & ~((v_channel >= 250) & (s_channel <= 25))
        valid_count = int(np.sum(valid_mask))

        if valid_count < 100:
            # Fall back to whole crop
            valid_mask = np.ones_like(v_channel, dtype=bool)
            valid_count = len(v_channel)

        valid_h = h_channel[valid_mask]
        valid_s = s_channel[valid_mask]
        valid_v = v_channel[valid_mask]

        # 1. Circular Mean Hue
        angles = valid_h.astype(float) * (2.0 * math.pi / 180.0)
        mean_cos = float(np.mean(np.cos(angles)))
        mean_sin = float(np.mean(np.sin(angles)))
        mean_angle = math.atan2(mean_sin, mean_cos) % (2.0 * math.pi)
        mean_hue = (mean_angle / (2.0 * math.pi)) * 180.0

        median_sat = float(np.median(valid_s))
        median_val = float(np.median(valid_v))

        # 2. Color Matching Logic
        bounds = STANDARD_COLOR_BOUNDS.get(expected_color_name, {"type": "achromatic", "s_max": 50})
        is_match = False
        delta_e = 0.0

        if bounds["type"] == "achromatic":
            if expected_color_name == "WHITE":
                # White: high/medium value, low saturation
                s_thresh = bounds.get("s_max", 65)
                v_thresh = bounds.get("v_min", 85)
                delta_e = max(0.0, median_sat - s_thresh) * 1.5 + max(0.0, v_thresh - median_val)
                is_match = (median_sat <= s_thresh) and (median_val >= v_thresh) and (delta_e <= self.settings.MAX_HSV_COLOR_DELTA)
            elif expected_color_name == "BLACK":
                # ponytail: Black vehicle daylight reflection tolerance (glossy clearcoat raises V to 75-95, sky reflections are low sat)
                s_thresh = bounds.get("s_max", 45)
                v_thresh = bounds.get("v_max", 100)
                is_match = (median_sat <= s_thresh) and (median_val <= v_thresh)
                delta_e = max(0.0, median_val - float(v_thresh)) + max(0.0, median_sat - float(s_thresh))
            elif expected_color_name in ("SILVER", "GREY", "GRAY"):
                # Silver/Grey: low saturation, mid value
                is_match = (median_sat <= bounds.get("s_max", 55)) and (bounds.get("v_min", 60) <= median_val <= bounds.get("v_max", 220))
                delta_e = max(0.0, median_sat - 55.0)
            else:
                is_match = median_sat <= 50.0
                delta_e = max(0.0, median_sat - 50.0)
        else:
            # Chromatic color (RED, BLUE, GREEN, etc.)
            target_h = float(bounds.get("target_h", 0))
            # Circular hue distance in OpenCV scale [0, 180]
            delta_h = min(abs(mean_hue - target_h), 180.0 - abs(mean_hue - target_h))
            # Distance metric
            delta_e = math.sqrt((2.0 * delta_h) ** 2 + ((median_sat - 120.0) * 0.2) ** 2)
            is_match = (delta_h <= 20.0) and (median_sat >= bounds.get("s_min", 60))

        duration_ms = (time.perf_counter() - t0) * 1000.0
        failure_code = None if is_match else "S1_COLOR_MISMATCH"

        logger.info(
            f"ColorGrounding: expected={expected_color_name}, measured=(H={mean_hue:.1f}, S={median_sat:.1f}, V={median_val:.1f}), "
            f"match={is_match}, delta_e={delta_e:.1f} ({duration_ms:.2f}ms)"
        )

        return ColorValidationResult(
            is_color_match=is_match,
            expected_color_name=expected_color_name,
            measured_hue_circular_mean=mean_hue,
            measured_sat_median=median_sat,
            measured_val_median=median_val,
            delta_e_hsv=delta_e,
            valid_paint_pixel_count=valid_count,
            failure_code=failure_code,
            duration_ms=duration_ms,
        )

    validate_color = validate_paint_color

color_grounding_validator = ColorGroundingValidator()

