import time
from pathlib import Path
from typing import List, Tuple
import cv2
import numpy as np
from app.domain.vehicle_identity_continuity.config import stage1_settings
from app.domain.vehicle_identity_continuity.schemas import CutDetectionResult
from app.core.logging import logger

class CutDetector:
    """
    Gate 1: Fast CPU Continuity & Splice Firewall (< 100ms).
    Uses downsampled 320x180 frames, PySceneDetect content metric, global HSV correlation,
    4x4 spatial grid correlation, block SSIM, and freeze-frame detection.
    """
    def __init__(self):
        self.settings = stage1_settings

    def evaluate(self, video_path: Path) -> CutDetectionResult:
        t0 = time.perf_counter()

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return CutDetectionResult(
                is_continuous=False,
                failure_code="ESC-02",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            if fps <= 0 or fps > 240:
                fps = 30.0

            target_w, target_h = self.settings.DOWNSAMPLE_WIDTH, self.settings.DOWNSAMPLE_HEIGHT
            prev_bgr = None
            prev_hsv = None
            prev_global_hist = None

            min_global_corr = 1.0
            min_grid_p25_corr = 1.0
            min_ssim = 1.0
            max_scene_score = 0.0
            max_frozen_run = 0
            current_frozen_run = 0

            evaluated_frames = 0
            cut_indices: List[int] = []

            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                evaluated_frames += 1
                # Downsample to 320x180
                small_bgr = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
                small_hsv = cv2.cvtColor(small_bgr, cv2.COLOR_BGR2HSV)
                small_gray = cv2.cvtColor(small_bgr, cv2.COLOR_BGR2GRAY)

                # Compute 160-bin global HSV histogram (16 H, 4 S, 4 V -> 16+4+4 or 3D)
                # 30 H bins, 32 S bins = standard 2D/3D histogram
                hist = cv2.calcHist([small_hsv], [0, 1], None, [16, 10], [0, 180, 0, 256])
                cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

                if prev_bgr is not None:
                    # 1. Freeze Frame Check
                    diff_abs = np.mean(np.abs(small_gray.astype(float) - prev_gray.astype(float)))
                    if diff_abs < 0.2:
                        current_frozen_run += 1
                        if current_frozen_run > max_frozen_run:
                            max_frozen_run = current_frozen_run
                    else:
                        current_frozen_run = 0

                    # 2. Content Difference Score (PySceneDetect metric emulation)
                    # Computes delta HSV intensity per channel
                    delta_hsv = np.mean(np.abs(small_hsv.astype(float) - prev_hsv.astype(float)))
                    if delta_hsv > max_scene_score:
                        max_scene_score = delta_hsv

                    # 3. Global HSV Histogram Correlation
                    corr = float(cv2.compareHist(prev_global_hist, hist, cv2.HISTCMP_CORREL))
                    if corr < min_global_corr:
                        min_global_corr = corr

                    # Check for hard cut
                    is_cut = False
                    if delta_hsv >= self.settings.PYSCENEDETECT_THRESHOLD or corr < self.settings.MIN_GLOBAL_HSV_CORR:
                        is_cut = True

                    # 4. 4x4 Spatial Grid Correlation (detects subtle same-car splices)
                    grid_corrs = []
                    cell_w, cell_h = target_w // 4, target_h // 4
                    for r in range(4):
                        for c in range(4):
                            cell_prev = prev_hsv[r * cell_h : (r + 1) * cell_h, c * cell_w : (c + 1) * cell_w]
                            cell_curr = small_hsv[r * cell_h : (r + 1) * cell_h, c * cell_w : (c + 1) * cell_w]
                            h_p = cv2.calcHist([cell_prev], [0, 1], None, [8, 8], [0, 180, 0, 256])
                            h_c = cv2.calcHist([cell_curr], [0, 1], None, [8, 8], [0, 180, 0, 256])
                            cv2.normalize(h_p, h_p, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
                            cv2.normalize(h_c, h_c, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
                            g_corr = float(cv2.compareHist(h_p, h_c, cv2.HISTCMP_CORREL))
                            grid_corrs.append(g_corr)

                    p25_corr = float(np.percentile(grid_corrs, 25))
                    if p25_corr < min_grid_p25_corr:
                        min_grid_p25_corr = p25_corr

                    if p25_corr < self.settings.MIN_GRID_P25_HSV_CORR:
                        # Trigger SSIM on 8x8 block grid
                        ssim_val = self._compute_quick_ssim(small_gray, prev_gray)
                        if ssim_val < min_ssim:
                            min_ssim = ssim_val
                        if ssim_val < self.settings.MIN_TRIGGERED_SSIM:
                            is_cut = True

                    if is_cut:
                        cut_indices.append(evaluated_frames)

                prev_bgr = small_bgr
                prev_hsv = small_hsv
                prev_gray = small_gray
                prev_global_hist = hist

            duration_ms = (time.perf_counter() - t0) * 1000.0

            # Failure classification priority: Cut > Histogram > SSIM > Freeze
            specific_code = None
            if max_scene_score >= self.settings.PYSCENEDETECT_THRESHOLD:
                specific_code = "S1_CUT_PYSCENEDETECT_TRIGGER"
            elif min_global_corr < self.settings.MIN_GLOBAL_HSV_CORR:
                specific_code = "S1_CUT_HISTOGRAM_DROP"
            elif min_ssim < self.settings.MIN_TRIGGERED_SSIM:
                specific_code = "S1_CUT_SPATIAL_SSIM_DROP"
            elif max_frozen_run > self.settings.MAX_FROZEN_FRAMES:
                cut_indices.append(-1)  # Marker for frozen frame
                specific_code = "S1_CUT_FREEZE_FRAME_DETECTED"
            elif len(cut_indices) > 0:
                specific_code = "S1_CUT_HISTOGRAM_DROP"

            is_continuous = len(cut_indices) == 0
            failure_code = None if is_continuous else (specific_code or "S1_CUT_HISTOGRAM_DROP")

            logger.info(
                f"CutDetector: continuous={is_continuous}, frames={evaluated_frames}, "
                f"min_corr={min_global_corr:.3f}, min_p25={min_grid_p25_corr:.3f}, "
                f"max_scene={max_scene_score:.1f}, max_freeze={max_frozen_run} ({duration_ms:.2f}ms)"
            )

            return CutDetectionResult(
                is_continuous=is_continuous,
                evaluated_frames=evaluated_frames,
                effective_fps=fps,
                min_global_hsv_corr=min_global_corr,
                min_grid_p25_hsv_corr=min_grid_p25_corr,
                min_triggered_ssim=min_ssim,
                max_pyscenedetect_score=max_scene_score,
                max_frozen_frame_run=max_frozen_run,
                cut_frame_indices=cut_indices,
                failure_code=failure_code,
                duration_ms=duration_ms,
            )

        finally:
            cap.release()

    def _compute_quick_ssim(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """Fast SSIM approximation on downsampled grayscale images."""
        c1 = (0.01 * 255) ** 2
        c2 = (0.03 * 255) ** 2

        img1 = img1.astype(float)
        img2 = img2.astype(float)

        mu1 = cv2.GaussianBlur(img1, (11, 11), 1.5)
        mu2 = cv2.GaussianBlur(img2, (11, 11), 1.5)

        mu1_sq = mu1 ** 2
        mu2_sq = mu2 ** 2
        mu1_mu2 = mu1 * mu2

        sigma1_sq = cv2.GaussianBlur(img1 ** 2, (11, 11), 1.5) - mu1_sq
        sigma2_sq = cv2.GaussianBlur(img2 ** 2, (11, 11), 1.5) - mu2_sq
        sigma12 = cv2.GaussianBlur(img1 * img2, (11, 11), 1.5) - mu1_mu2

        ssim_map = ((2 * mu1_mu2 + c1) * (2 * sigma12 + c2)) / (
            (mu1_sq + mu2_sq + c1) * (sigma1_sq + sigma2_sq + c2)
        )
        return float(np.mean(ssim_map))

    verify_continuity = evaluate

cut_detector = CutDetector()

