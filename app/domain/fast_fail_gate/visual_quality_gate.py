import time
from pathlib import Path
from typing import List, Tuple
import cv2
import numpy as np
from app.core.config import settings
from app.domain.fast_fail_gate.schemas import (
    VisualGateReport,
    SampledFrameMetric,
    FastFailFailureCode,
    ContainerGateReport,
)
from app.core.logging import logger

class VisualQualityValidator:
    def __init__(self):
        self.settings = settings

    def validate(self, video_path: Path, container_report: ContainerGateReport) -> VisualGateReport:
        t0 = time.perf_counter()
        failure_codes: List[FastFailFailureCode] = []

        if not video_path.exists():
            return VisualGateReport(
                passed=False,
                failure_codes=[FastFailFailureCode.CONTAINER_PARSE_FAILED],
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        sampled_metrics = self._execute_single_pass_scan(video_path, container_report)

        # ponytail: quorum attack prevention — if video terminated early and did not yield all planned sample points, fail container parse
        if not sampled_metrics or len(sampled_metrics) < len(self.settings.SAMPLE_NORMALIZED_TIMESTAMPS):
            logger.warning(
                f"Visual Quality on {video_path.name}: insufficient samples ({len(sampled_metrics)}/{len(self.settings.SAMPLE_NORMALIZED_TIMESTAMPS)})"
            )
            return VisualGateReport(
                passed=False,
                failure_codes=[FastFailFailureCode.CONTAINER_PARSE_FAILED],
                sampled_frames=sampled_metrics or [],
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        dark_count = sum(1 for m in sampled_metrics if m.is_dark)
        bright_count = sum(1 for m in sampled_metrics if m.is_overexposed)
        blurry_count = sum(1 for m in sampled_metrics if m.is_blurry)

        total_samples = len(sampled_metrics)
        quorum_threshold = (total_samples // 2) + 1  # >= 3 for 5 samples

        if dark_count >= quorum_threshold:
            failure_codes.append(FastFailFailureCode.VIDEO_TOO_DARK)
        if bright_count >= quorum_threshold:
            failure_codes.append(FastFailFailureCode.VIDEO_TOO_BRIGHT)
        if blurry_count >= quorum_threshold:
            failure_codes.append(FastFailFailureCode.VIDEO_TOO_BLURRY)

        mean_luminance = float(np.mean([m.mean_luminance_y for m in sampled_metrics]))
        mean_sharpness = float(np.mean([m.laplacian_variance for m in sampled_metrics]))
        duration_ms = (time.perf_counter() - t0) * 1000.0
        passed = len(failure_codes) == 0

        logger.info(
            f"Visual Quality on {video_path.name}: passed={passed}, mean_Y={mean_luminance:.1f}, "
            f"mean_Lap={mean_sharpness:.1f}, dark={dark_count}/{total_samples}, "
            f"bright={bright_count}/{total_samples}, blurry={blurry_count}/{total_samples} ({duration_ms:.2f}ms)"
        )

        return VisualGateReport(
            passed=passed,
            failure_codes=failure_codes,
            sampled_frames=sampled_metrics,
            mean_luminance_aggregate=mean_luminance,
            mean_sharpness_aggregate=mean_sharpness,
            dark_frame_count=dark_count,
            bright_frame_count=bright_count,
            blurry_frame_count=blurry_count,
            duration_ms=duration_ms,
        )

    def _execute_single_pass_scan(
        self, video_path: Path, container_report: ContainerGateReport
    ) -> List[SampledFrameMetric]:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return []

        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            if fps <= 0 or fps > 240:
                fps = container_report.effective_fps or 30.0

            if total_frames <= 0 and container_report.duration_sec > 0:
                total_frames = int(container_report.duration_sec * fps)

            if total_frames < 5:
                # Video too short to sample 5 distinct frames
                total_frames = max(5, total_frames)

            sample_positions = self.settings.SAMPLE_NORMALIZED_TIMESTAMPS
            target_indices = {
                int(pos * (total_frames - 1)): (idx, pos)
                for idx, pos in enumerate(sample_positions)
            }
            max_target_index = max(target_indices.keys())

            metrics: List[SampledFrameMetric] = []
            current_frame_idx = 0

            while current_frame_idx <= max_target_index:
                if current_frame_idx in target_indices:
                    # Target frame: grab and decode
                    ret = cap.grab()
                    if not ret:
                        break
                    ret_retrieve, frame_bgr = cap.retrieve()
                    if ret_retrieve and frame_bgr is not None:
                        s_idx, s_pos = target_indices[current_frame_idx]
                        metric = self._compute_frame_metric(
                            frame_bgr=frame_bgr,
                            sample_index=s_idx,
                            normalized_pos=s_pos,
                            frame_number=current_frame_idx,
                            fps=fps,
                        )
                        metrics.append(metric)
                else:
                    # Non-target frame: advance pointer cheaply without pixel decoding
                    ret = cap.grab()
                    if not ret:
                        break

                current_frame_idx += 1

            return sorted(metrics, key=lambda m: m.sample_index)

        finally:
            cap.release()

    def _compute_frame_metric(
        self, frame_bgr: np.ndarray, sample_index: int, normalized_pos: float, frame_number: int, fps: float
    ) -> SampledFrameMetric:
        # 1. YUV Luminance check
        yuv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2YUV)
        mean_y = float(np.mean(yuv[:, :, 0]))

        # 2. Scale-normalized Laplacian sharpness check
        h, w = frame_bgr.shape[:2]
        # Normalize to 720p height (720) for consistent Laplacian gradient scale
        target_h = 720
        target_w = int(w * (target_h / h))
        if target_w > 0 and target_h > 0:
            frame_norm = cv2.resize(frame_bgr, (target_w, target_h), interpolation=cv2.INTER_AREA)
        else:
            frame_norm = frame_bgr

        gray = cv2.cvtColor(frame_norm, cv2.COLOR_BGR2GRAY)
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        timestamp_sec = frame_number / fps if fps > 0 else 0.0
        is_dark = mean_y < self.settings.LUMINANCE_MIN_THRESHOLD
        is_overexposed = mean_y > self.settings.LUMINANCE_MAX_THRESHOLD
        is_blurry = laplacian_var < self.settings.SHARPNESS_MIN_THRESHOLD

        return SampledFrameMetric(
            sample_index=sample_index,
            normalized_pos=normalized_pos,
            frame_number=frame_number,
            timestamp_sec=timestamp_sec,
            mean_luminance_y=mean_y,
            laplacian_variance=laplacian_var,
            is_dark=is_dark,
            is_overexposed=is_overexposed,
            is_blurry=is_blurry,
        )

visual_quality_validator = VisualQualityValidator()

