import asyncio
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from app.domain.vehicle_identity_continuity.config import stage1_settings
from app.domain.vehicle_identity_continuity.schemas import (
    TrackingAndKeyframeResult,
    PolicyGroundingContext,
)
from app.domain.vehicle_identity_continuity.keyframe_selector import keyframe_selector
from app.core.logging import logger

class ObjectTracker:
    def __init__(self, yolo_model: Optional[YOLO] = None):
        self.settings = stage1_settings
        self._yolo = yolo_model
        self._gpu_lock = asyncio.Semaphore(1)

    def get_yolo(self) -> YOLO:
        if self._yolo is None:
            self._yolo = YOLO(self.settings.YOLO_MODEL_PATH)
            if torch.cuda.is_available():
                self._yolo.to("cuda")
        return self._yolo

    def reset_tracker_state(self, yolo: YOLO) -> None:
        """Explicitly resets ByteTrack internal Kalman state before frame 0."""
        try:
            if hasattr(yolo, "predictor") and yolo.predictor and hasattr(yolo.predictor, "trackers"):
                for tracker in yolo.predictor.trackers:
                    if hasattr(tracker, "reset"):
                        tracker.reset()
                logger.debug("ByteTrack internal tracker state reset successfully.")
        except Exception as e:
            logger.warning(f"Could not reset ByteTrack state: {e}")

    def track_and_extract_keyframes(
        self,
        video_path: Path,
        claim_id: str,
        grounding_context: PolicyGroundingContext,
        plate_deferred: bool = False,
    ) -> TrackingAndKeyframeResult:
        t0 = time.perf_counter()
        yolo = self.get_yolo()

        # Reset ByteTrack singleton state
        self.reset_tracker_state(yolo)

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return TrackingAndKeyframeResult(
                is_persistent=False,
                failure_code="ESC-02",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if fps <= 0 or fps > 240:
            fps = 30.0
        cap.release()

        target_track_id: Optional[int] = None
        frames_tracked = 0
        wide_track_lost_streak = 0
        max_wide_lost_streak = 0
        last_area_ratio = 0.0
        closeup_handoff_triggered = False
        switched_to_other_vehicle = False

        # Keyframe candidate storage: {view: (score, frame_bgr)}
        best_candidates: Dict[str, Tuple[float, np.ndarray]] = {}

        try:
            # Run strided tracking
            generator = yolo.track(
                source=str(video_path),
                stream=True,
                vid_stride=self.settings.VID_STRIDE,
                persist=True,
                conf=0.35,
                imgsz=640,
                verbose=False,
            )

            frame_idx = 0
            for result in generator:
                frame_idx += self.settings.VID_STRIDE
                orig_frame = result.orig_img
                h_f, w_f = orig_frame.shape[:2]
                frame_area = h_f * w_f

                # Find vehicle detections
                boxes = result.boxes
                found_target = False
                current_box = None
                current_area = 0.0

                if boxes is not None and len(boxes) > 0:
                    for box in boxes:
                        cls_id = int(box.cls[0].item())
                        if cls_id in (2, 5, 7):  # car, bus, truck
                            bx1, by1, bx2, by2 = [int(v.item()) for v in box.xyxy[0]]
                            box_area = (bx2 - bx1) * (by2 - by1)
                            t_id = int(box.id[0].item()) if (box.id is not None and len(box.id) > 0) else None

                            if target_track_id is None and t_id is not None:
                                target_track_id = t_id

                            if target_track_id is not None and t_id == target_track_id:
                                found_target = True
                                current_box = (bx1, by1, bx2, by2)
                                current_area = box_area / frame_area
                                break
                            elif target_track_id is None and (box_area / frame_area) >= 0.15:
                                # Primary vehicle candidate
                                target_track_id = t_id or 1
                                found_target = True
                                current_box = (bx1, by1, bx2, by2)
                                current_area = box_area / frame_area
                                break
                            elif target_track_id is not None and t_id != target_track_id and (box_area / frame_area) >= 0.20:
                                switched_to_other_vehicle = True

                if found_target and current_box is not None:
                    frames_tracked += 1
                    wide_track_lost_streak = 0
                    last_area_ratio = current_area
                    if current_area >= self.settings.CLOSEUP_ZOOM_AREA_RATIO:
                        closeup_handoff_triggered = True

                    # Score frame inline for keyframe buffers
                    sharpness, glare, quality = keyframe_selector.score_frame(orig_frame)

                    # Partition views by timeline & area
                    rel_t = frame_idx / total_frames if total_frames > 0 else 0.0

                    # 1. Bumper view (early video, rel_t <= 0.35)
                    if rel_t <= 0.35:
                        view = "front_bumper"
                        if view not in best_candidates or quality > best_candidates[view][0]:
                            best_candidates[view] = (quality, orig_frame.copy())

                    # 2. Side body panel (mid walkaround, 0.25 <= rel_t <= 0.75)
                    if 0.25 <= rel_t <= 0.75:
                        view = "side_body_panel"
                        if view not in best_candidates or quality > best_candidates[view][0]:
                            best_candidates[view] = (quality, orig_frame.copy())

                    # 3. Macro closeup view (high area ratio or late video)
                    if current_area >= 0.45 or rel_t >= 0.65:
                        view = "damage_closeup_primary"
                        if view not in best_candidates or quality > best_candidates[view][0]:
                            best_candidates[view] = (quality, orig_frame.copy())

                else:
                    # Vehicle not detected in this strided frame
                    if last_area_ratio >= self.settings.CLOSEUP_ZOOM_AREA_RATIO:
                        # Close-up zoom handoff: claimant walked very close to door!
                        closeup_handoff_triggered = True
                        wide_track_lost_streak = 0
                        # Still capture potential closeup keyframes
                        sharpness, glare, quality = keyframe_selector.score_frame(orig_frame)
                        view = "damage_closeup_primary"
                        if view not in best_candidates or quality > best_candidates[view][0]:
                            best_candidates[view] = (quality, orig_frame.copy())
                    else:
                        wide_track_lost_streak += self.settings.VID_STRIDE
                        if wide_track_lost_streak > max_wide_lost_streak:
                            max_wide_lost_streak = wide_track_lost_streak

            # Save winning keyframes atomically
            saved_paths: Dict[str, str] = {}
            for view_name, (_, frame_img) in best_candidates.items():
                p = keyframe_selector.save_keyframe_atomically(frame_img, claim_id, view_name)
                saved_paths[view_name] = str(p)

            # Check persistence
            is_persistent = (max_wide_lost_streak <= self.settings.MAX_WIDE_TRACK_LOST_FRAMES) and not (switched_to_other_vehicle and max_wide_lost_streak > 3)
            if is_persistent:
                failure_code = None
            elif max_wide_lost_streak > self.settings.MAX_WIDE_TRACK_LOST_FRAMES:
                failure_code = "S1_TRACK_LOST_EXCEEDED"
            elif switched_to_other_vehicle:
                failure_code = "S1_TRACK_ID_SWITCHED"
            else:
                failure_code = "S1_TRACK_LOST_EXCEEDED"
            duration_ms = (time.perf_counter() - t0) * 1000.0

            logger.info(
                f"ObjectTracker: persistent={is_persistent}, tracked={frames_tracked}, "
                f"lost_streak={max_wide_lost_streak}, closeup_handoff={closeup_handoff_triggered}, "
                f"keyframes_saved={list(saved_paths.keys())} ({duration_ms:.2f}ms)"
            )

            return TrackingAndKeyframeResult(
                is_persistent=is_persistent,
                target_track_id=target_track_id or 1,
                frames_tracked=frames_tracked,
                track_lost_count=max_wide_lost_streak,
                closeup_handoff_triggered=closeup_handoff_triggered,
                saved_keyframes=saved_paths,
                failure_code=failure_code,
                duration_ms=duration_ms,
            )

        except Exception as e:
            logger.error(f"Tracking error on {video_path}: {e}")
            return TrackingAndKeyframeResult(
                is_persistent=False,
                failure_code="ESC-02",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

object_tracker = ObjectTracker()

