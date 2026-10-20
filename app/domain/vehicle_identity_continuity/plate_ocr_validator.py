import re
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from app.domain.vehicle_identity_continuity.config import stage1_settings
from app.domain.vehicle_identity_continuity.schemas import PlateValidationResult
from app.core.logging import logger

HOMOGLYPH_PAIRS = {
    ("O", "0"): 0.25, ("0", "O"): 0.25,
    ("I", "1"): 0.25, ("1", "I"): 0.25,
    ("B", "8"): 0.25, ("8", "B"): 0.25,
    ("Z", "2"): 0.25, ("2", "Z"): 0.25,
    ("D", "0"): 0.30, ("0", "D"): 0.30,
    ("S", "5"): 0.25, ("5", "S"): 0.25,
    ("G", "6"): 0.30, ("6", "G"): 0.30,
}

def clean_plate_string(raw: str) -> str:
    """Removes non-alphanumeric characters and converts to uppercase."""
    return re.sub(r"[^A-Za-z0-9]", "", raw).upper()

def homoglyph_weighted_distance(s1: str, s2: str) -> float:
    """
    Computes Levenshtein edit distance with reduced cost for optical OCR homoglyphs.
    """
    s1, s2 = clean_plate_string(s1), clean_plate_string(s2)
    m, n = len(s1), len(s2)
    dp = [[0.0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = float(i)
    for j in range(n + 1):
        dp[0][j] = float(j)

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            c1, c2 = s1[i - 1], s2[j - 1]
            if c1 == c2:
                cost = 0.0
            else:
                cost = HOMOGLYPH_PAIRS.get((c1, c2), 1.0)
            dp[i][j] = min(
                dp[i - 1][j] + 1.0,      # deletion
                dp[i][j - 1] + 1.0,      # insertion
                dp[i - 1][j - 1] + cost  # substitution
            )

    return dp[m][n]


class PlateOCRValidator:
    def __init__(self, yolo_model: Optional[YOLO] = None):
        self.settings = stage1_settings
        self._yolo = yolo_model
        self._ocr_reader = None

    def get_yolo(self) -> YOLO:
        if self._yolo is None:
            self._yolo = YOLO(self.settings.YOLO_MODEL_PATH)
            if torch.cuda.is_available():
                self._yolo.to("cuda")
        return self._yolo

    def get_ocr_reader(self):
        if self._ocr_reader is None:
            try:
                import easyocr
                # Initialize EasyOCR with English and GPU if available
                gpu = torch.cuda.is_available()
                self._ocr_reader = easyocr.Reader(["en"], gpu=gpu, verbose=False)
            except Exception as e:
                logger.warning(f"EasyOCR initialization failed: {e}")
                self._ocr_reader = None
        return self._ocr_reader

    def validate_initial_window(
        self,
        video_path: Path,
        expected_plate: str,
        initial_seconds: float = 3.5,
    ) -> PlateValidationResult:
        t0 = time.perf_counter()
        expected_clean = clean_plate_string(expected_plate)

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return PlateValidationResult(
                is_verified=False,
                expected_plate=expected_plate,
                failure_code="ESC-01",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            if fps <= 0 or fps > 240:
                fps = 30.0

            max_frame_idx = int(initial_seconds * fps)
            # Sample up to 8 frames in initial window
            sample_step = max(1, max_frame_idx // 8)

            yolo = self.get_yolo()
            ocr = self.get_ocr_reader()

            best_match_candidate: Optional[str] = None
            lowest_edit_cost: float = 999.0
            highest_conf: float = 0.0
            found_any_vehicle: bool = False
            anchor_frame_idx: int = 0
            anchor_bbox: Optional[Tuple[int, int, int, int]] = None

            current_frame_idx = 0
            while current_frame_idx <= max_frame_idx:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                if current_frame_idx % sample_step == 0:
                    h, w = frame.shape[:2]
                    frame_area = h * w

                    # 1. Run YOLO to find vehicle
                    results = yolo.predict(frame, imgsz=640, verbose=False, conf=0.35)
                    boxes = results[0].boxes
                    vehicle_box = None

                    # COCO classes: 2=car, 3=motorcycle, 5=bus, 7=truck
                    for box in boxes:
                        cls_id = int(box.cls[0].item())
                        if cls_id in (2, 5, 7):
                            bx1, by1, bx2, by2 = [int(v.item()) for v in box.xyxy[0]]
                            box_area = (bx2 - bx1) * (by2 - by1)
                            if (box_area / frame_area) >= self.settings.MIN_VEHICLE_AREA_RATIO:
                                vehicle_box = (bx1, by1, bx2, by2)
                                found_any_vehicle = True
                                break

                    if vehicle_box and ocr:
                        vx1, vy1, vx2, vy2 = vehicle_box
                        vh = vy2 - vy1
                        # Crop vehicle ROI (bumper zone: y_rel in [0.28, 0.96])
                        crop_y1 = max(0, int(vy1 + vh * self.settings.BUMPER_Y_REL_MIN))
                        crop_y2 = min(h, int(vy1 + vh * self.settings.BUMPER_Y_REL_MAX))
                        veh_roi = frame[crop_y1:crop_y2, vx1:vx2]

                        if veh_roi.size > 0:
                            # Run OCR on vehicle bumper ROI
                            detections = ocr.readtext(veh_roi)
                            merged_text, conf = self._extract_and_merge_plate(detections, veh_roi.shape[:2])

                            if merged_text:
                                clean_cand = clean_plate_string(merged_text)
                                cost = homoglyph_weighted_distance(clean_cand, expected_clean)

                                if cost < lowest_edit_cost:
                                    lowest_edit_cost = cost
                                    best_match_candidate = clean_cand
                                    highest_conf = conf
                                    anchor_frame_idx = current_frame_idx
                                    anchor_bbox = vehicle_box

                                # Exact match shortcut
                                if cost <= 0.5:
                                    break

                current_frame_idx += 1

            duration_ms = (time.perf_counter() - t0) * 1000.0

            if not found_any_vehicle:
                # No car in initial window -> check if reverse walkaround or defer
                logger.warning("No vehicle detected in initial 3.5s window.")
                return PlateValidationResult(
                    is_verified=False,
                    deferred_to_late_track=True,
                    expected_plate=expected_plate,
                    failure_code="S1_NO_VEHICLE_DETECTED",
                    duration_ms=duration_ms,
                )

            # Check match quality
            if lowest_edit_cost <= self.settings.MAX_HOMOGLYPH_EDIT_COST:
                # Matched within allowable homoglyph tolerance!
                logger.info(
                    f"Plate verified: expected={expected_clean}, candidate={best_match_candidate}, "
                    f"cost={lowest_edit_cost:.2f}, conf={highest_conf:.2f} ({duration_ms:.2f}ms)"
                )
                return PlateValidationResult(
                    is_verified=True,
                    deferred_to_late_track=False,
                    expected_plate=expected_plate,
                    extracted_plate=best_match_candidate,
                    ocr_confidence=highest_conf,
                    homoglyph_edit_cost=lowest_edit_cost,
                    is_spatially_grounded_on_vehicle=True,
                    anchor_frame_idx=anchor_frame_idx,
                    anchor_vehicle_bbox=anchor_bbox,
                    duration_ms=duration_ms,
                )

            if best_match_candidate and len(best_match_candidate) >= 7 and lowest_edit_cost > self.settings.MAX_HOMOGLYPH_EDIT_COST:
                # Clearly legible WRONG plate -> fast-fail immediately with S1_PLATE_MISMATCH
                logger.warning(
                    f"Wrong plate detected: expected={expected_clean}, found={best_match_candidate}, cost={lowest_edit_cost:.2f}"
                )
                return PlateValidationResult(
                    is_verified=False,
                    deferred_to_late_track=False,
                    expected_plate=expected_plate,
                    extracted_plate=best_match_candidate,
                    ocr_confidence=highest_conf,
                    homoglyph_edit_cost=lowest_edit_cost,
                    failure_code="S1_PLATE_MISMATCH",
                    duration_ms=duration_ms,
                )

            # Low confidence or blurred plate: defer to tracking phase
            logger.info(
                f"Plate inconclusive in initial window (cand={best_match_candidate}, cost={lowest_edit_cost:.2f}), deferring to tracking."
            )
            return PlateValidationResult(
                is_verified=False,
                deferred_to_late_track=True,
                expected_plate=expected_plate,
                extracted_plate=best_match_candidate,
                ocr_confidence=highest_conf,
                homoglyph_edit_cost=lowest_edit_cost,
                anchor_frame_idx=anchor_frame_idx,
                anchor_vehicle_bbox=anchor_bbox,
                duration_ms=duration_ms,
            )

        finally:
            cap.release()

    def _extract_and_merge_plate(
        self, detections: List[Any], roi_shape: Tuple[int, int]
    ) -> Tuple[Optional[str], float]:
        """
        Handles single-line and 2-line Indian HSRP stacked plate polygon merging.
        """
        if not detections:
            return None, 0.0

        candidates = []
        for det in detections:
            bbox, text, conf = det
            clean = clean_plate_string(text)
            if len(clean) >= 2 and float(conf) >= 0.15:
                # Compute bounding rectangle
                pts = np.array(bbox)
                x_min, y_min = pts.min(axis=0)
                x_max, y_max = pts.max(axis=0)
                candidates.append({
                    "text": clean,
                    "conf": float(conf),
                    "x1": x_min, "y1": y_min,
                    "x2": x_max, "y2": y_max,
                    "w": x_max - x_min, "h": y_max - y_min,
                })

        if not candidates:
            return None, 0.0

        # Try merging 2-line stacked plates (top and bottom boxes)
        candidates_sorted = sorted(candidates, key=lambda c: c["y1"])
        merged_candidates = []
        for i in range(len(candidates_sorted)):
            for j in range(i + 1, len(candidates_sorted)):
                c1, c2 = candidates_sorted[i], candidates_sorted[j]
                # Horizontal overlap
                overlap_w = max(0, min(c1["x2"], c2["x2"]) - max(c1["x1"], c2["x1"]))
                min_w = min(c1["w"], c2["w"])
                if min_w > 0 and (overlap_w / min_w) >= self.settings.HSRP_MIN_HORIZONTAL_OVERLAP:
                    # Vertical gap
                    vert_gap = max(0, c2["y1"] - c1["y2"])
                    avg_h = (c1["h"] + c2["h"]) / 2.0
                    if avg_h > 0 and (vert_gap / avg_h) <= self.settings.HSRP_MAX_VERTICAL_GAP_RATIO:
                        merged = c1["text"] + c2["text"]
                        merged_conf = (c1["conf"] + c2["conf"]) / 2.0
                        if len(merged) >= 7:
                            merged_candidates.append({"text": merged, "conf": merged_conf})

        # Combine single full plates (>= 8 chars) and merged candidates, pick highest confidence
        all_full = [c for c in candidates if len(c["text"]) >= 8] + merged_candidates
        if all_full:
            best_full = max(all_full, key=lambda c: c["conf"])
            return best_full["text"], best_full["conf"]

        # Fallback to the highest-confidence candidate
        best = max(candidates, key=lambda c: c["conf"])
        return best["text"], best["conf"]

plate_ocr_validator = PlateOCRValidator()

