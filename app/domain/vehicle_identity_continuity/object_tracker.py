import asyncio
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
import cv2
import numpy as np
import torch
from ultralytics import YOLO
from app.domain.vehicle_identity_continuity.config import stage1_settings
from app.domain.vehicle_identity_continuity.schemas import (
    TrackingAndKeyframeResult,
    PolicyGroundingContext,
    PlateValidationResult,
)
from app.domain.vehicle_identity_continuity.keyframe_selector import keyframe_selector
from app.domain.vehicle_identity_continuity.plate_ocr_validator import plate_ocr_validator
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

    def _select_canonical_keyframes(
        self,
        candidates: List[Dict[str, Any]],
        total_frames: int,
        plate_deferred: bool,
        plate_anchor_frame: Optional[int],
        closeup_handoff_triggered: bool,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Selects 3 distinct canonical keyframes satisfying the physical walkaround zones
        and the strict non-duplication invariant (|f_i - f_j| > 20).
        """
        def is_front_bumper(r: Dict[str, Any]) -> bool:
            if plate_deferred and plate_anchor_frame is not None:
                return abs(r["frame_idx"] - plate_anchor_frame) <= 30
            return r["rel_t"] <= 0.33

        def is_side_panel(r: Dict[str, Any]) -> bool:
            if 0.33 < r["rel_t"] <= 0.67:
                if plate_anchor_frame is not None and abs(r["frame_idx"] - plate_anchor_frame) <= 30:
                    return False
                return True
            return False

        def is_closeup(r: Dict[str, Any]) -> bool:
            return r["area_ratio"] >= 0.45 or closeup_handoff_triggered or r["rel_t"] > 0.67

        cands_fb = [r for r in candidates if is_front_bumper(r)]
        cands_sb = [r for r in candidates if is_side_panel(r)]
        cands_dc = [r for r in candidates if is_closeup(r)]

        for r in cands_fb:
            r["fb_score"] = r["quality"] + (500.0 if (plate_anchor_frame is not None and r["frame_idx"] == plate_anchor_frame) else 0.0)

        cands_fb.sort(key=lambda r: r.get("fb_score", r["quality"]), reverse=True)
        cands_sb.sort(key=lambda r: r["quality"], reverse=True)
        cands_dc.sort(key=lambda r: r["quality"], reverse=True)

        best_triplet = None
        best_score = -1.0

        top_fb = cands_fb[:15]
        top_sb = cands_sb[:15]
        top_dc = cands_dc[:15]

        for fb in top_fb:
            f_fb = fb["frame_idx"]
            for sb in top_sb:
                f_sb = sb["frame_idx"]
                if abs(f_fb - f_sb) <= 20:
                    continue
                for dc in top_dc:
                    f_dc = dc["frame_idx"]
                    if abs(f_fb - f_dc) <= 20 or abs(f_sb - f_dc) <= 20:
                        continue
                    score = fb.get("fb_score", fb["quality"]) + sb["quality"] + dc["quality"]
                    if score > best_score:
                        best_score = score
                        best_triplet = (fb, sb, dc)

        chosen: Dict[str, Dict[str, Any]] = {}
        if best_triplet is not None:
            chosen["front_bumper"] = best_triplet[0]
            chosen["side_body_panel"] = best_triplet[1]
            chosen["damage_closeup_primary"] = best_triplet[2]
        else:
            selected_frames: List[int] = []
            for view_name, cand_list in [
                ("front_bumper", top_fb),
                ("side_body_panel", top_sb),
                ("damage_closeup_primary", top_dc),
            ]:
                picked = None
                for c in cand_list:
                    if all(abs(c["frame_idx"] - sf) > 20 for sf in selected_frames):
                        picked = c
                        break
                if picked is not None:
                    chosen[view_name] = picked
                    selected_frames.append(picked["frame_idx"])

            for view_name in ["front_bumper", "side_body_panel", "damage_closeup_primary"]:
                if view_name not in chosen:
                    valid_fallbacks = [
                        r for r in candidates
                        if all(abs(r["frame_idx"] - sf) > 20 for sf in selected_frames)
                    ]
                    if valid_fallbacks:
                        def fallback_rank(r: Dict[str, Any]) -> Tuple[int, float]:
                            min_dist = min(abs(r["frame_idx"] - sf) for sf in selected_frames) if selected_frames else 100
                            return (min_dist, r["quality"])
                        best_fb_cand = max(valid_fallbacks, key=fallback_rank)
                        chosen[view_name] = best_fb_cand
                        selected_frames.append(best_fb_cand["frame_idx"])
                    elif candidates:
                        chosen[view_name] = candidates[0]

        return chosen

    def _curate_trajectory_keyframes(
        self,
        candidates: List[Dict[str, Any]],
        total_frames: int,
        n_curated: int = 15,
    ) -> List[Dict[str, Any]]:
        """
        Selects adaptive non-redundant keyframes distributed across the vehicle walkaround trajectory,
        enforcing adaptive minimum temporal separation between frames.
        """
        if not candidates:
            return []

        selected: List[Dict[str, Any]] = []
        selected_indices = set()
        min_sep = max(12, int(total_frames / (n_curated * 1.8)))

        sorted_cands = sorted(candidates, key=lambda c: c["quality"], reverse=True)

        for bin_idx in range(n_curated):
            t_min = bin_idx / n_curated
            t_max = (bin_idx + 1) / n_curated
            bin_cands = [c for c in sorted_cands if t_min <= c["rel_t"] <= t_max]

            picked = None
            for c in bin_cands:
                if all(abs(c["frame_idx"] - sf) >= min_sep for sf in selected_indices):
                    picked = c
                    break
            if picked is not None:
                selected.append(picked)
                selected_indices.add(picked["frame_idx"])

        while len(selected) < n_curated:
            valid = [c for c in sorted_cands if all(abs(c["frame_idx"] - sf) >= min_sep for sf in selected_indices)]
            if not valid:
                break
            best_cand = max(
                valid,
                key=lambda c: min(abs(c["frame_idx"] - sf) for sf in selected_indices) if selected_indices else c["quality"]
            )
            selected.append(best_cand)
            selected_indices.add(best_cand["frame_idx"])

        selected.sort(key=lambda c: c["frame_idx"])
        return selected

    def track_and_extract_keyframes(
        self,
        video_path: Path,
        claim_id: str,
        grounding_context: PolicyGroundingContext,
        plate_deferred: bool = False,
        plate_report: Optional[PlateValidationResult] = None,
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
        late_plate_verified = False
        plate_anchor_frame: Optional[int] = None
        stride_counter = 0

        # Rolling keyframe candidate pools
        candidate_pool: Dict[int, Dict[str, Any]] = {}
        bucketed_frames: Dict[int, List[int]] = {i: [] for i in range(10)}

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

                veh_candidates = []
                if boxes is not None and len(boxes) > 0:
                    for box in boxes:
                        cls_id = int(box.cls[0].item())
                        if cls_id in (2, 5, 7):  # car, bus, truck
                            bx1, by1, bx2, by2 = [int(v.item()) for v in box.xyxy[0]]
                            box_area = (bx2 - bx1) * (by2 - by1)
                            area_ratio = box_area / frame_area
                            t_id = int(box.id[0].item()) if (box.id is not None and len(box.id) > 0) else None
                            veh_candidates.append({
                                "box": (bx1, by1, bx2, by2),
                                "area": box_area,
                                "area_ratio": area_ratio,
                                "t_id": t_id,
                            })

                # ponytail: Foreground latching - pick vehicle candidate with max(box_area) >= 0.06/0.12
                # Prevents latching onto small background cars (e.g. t_id=1 in multi-car parking lots)
                min_ratio = min(0.12, self.settings.MIN_VEHICLE_AREA_RATIO)
                qualifying = [c for c in veh_candidates if c["area_ratio"] >= min_ratio]
                largest_candidate = max(qualifying, key=lambda c: c["area"]) if qualifying else None

                if target_track_id is None and largest_candidate is not None:
                    target_track_id = largest_candidate["t_id"]

                if target_track_id is not None:
                    target_match = next((c for c in veh_candidates if c["t_id"] == target_track_id), None)
                    if target_match is not None:
                        found_target = True
                        current_box = target_match["box"]
                        current_area = target_match["area_ratio"]
                    elif largest_candidate is not None and largest_candidate["area_ratio"] >= 0.20:
                        # Fallback: tracker reassigned id on turn, but foreground vehicle dominates frame
                        found_target = True
                        current_box = largest_candidate["box"]
                        current_area = largest_candidate["area_ratio"]
                        if largest_candidate["t_id"] is not None:
                            target_track_id = largest_candidate["t_id"]

                if not found_target and any(c["t_id"] != target_track_id and c["area_ratio"] >= 0.25 for c in veh_candidates):
                    switched_to_other_vehicle = True

                if found_target and current_box is not None:
                    frames_tracked += 1
                    wide_track_lost_streak = 0
                    last_area_ratio = current_area
                    if current_area >= self.settings.CLOSEUP_ZOOM_AREA_RATIO:
                        closeup_handoff_triggered = True

                    # ponytail: Late-track plate OCR grounding on reverse walkarounds
                    if plate_deferred and not late_plate_verified:
                        stride_counter += 1
                        if stride_counter % 2 == 0:
                            is_match, clean_cand, cost = plate_ocr_validator.verify_frame_plate(
                                orig_frame, current_box, grounding_context.registration_number
                            )
                            if is_match:
                                late_plate_verified = True
                                plate_anchor_frame = frame_idx
                                if plate_report is not None:
                                    plate_report.is_verified = True
                                    plate_report.extracted_plate = clean_cand
                                    plate_report.homoglyph_edit_cost = cost
                                    plate_report.failure_code = None
                                    plate_report.anchor_frame_idx = frame_idx
                                    plate_report.anchor_vehicle_bbox = current_box
                                logger.info(f"Late plate verification succeeded at frame {frame_idx}: {clean_cand} (cost={cost:.2f})")

                    # Score frame inline for keyframe buffers
                    sharpness, glare, quality = keyframe_selector.score_frame(orig_frame)
                    rel_t = frame_idx / total_frames if total_frames > 0 else 0.0

                    rec = {
                        "frame_idx": frame_idx,
                        "rel_t": rel_t,
                        "area_ratio": current_area,
                        "sharpness": sharpness,
                        "glare": glare,
                        "quality": quality,
                        "img": orig_frame.copy(),
                    }

                    b_idx = min(9, max(0, int(rel_t * 10)))
                    b_list = bucketed_frames[b_idx]
                    if len(b_list) < 4:
                        candidate_pool[frame_idx] = rec
                        b_list.append(frame_idx)
                    else:
                        worst_fidx = min(b_list, key=lambda f: candidate_pool[f]["quality"])
                        if quality > candidate_pool[worst_fidx]["quality"]:
                            b_list.remove(worst_fidx)
                            if not any(worst_fidx in bl for bl in bucketed_frames.values()):
                                candidate_pool.pop(worst_fidx, None)
                            candidate_pool[frame_idx] = rec
                            b_list.append(frame_idx)

                    if late_plate_verified and plate_anchor_frame == frame_idx:
                        candidate_pool[frame_idx] = rec
                    if current_area >= 0.45:
                        candidate_pool[frame_idx] = rec

                else:
                    # Vehicle not detected in this strided frame
                    if last_area_ratio >= self.settings.CLOSEUP_ZOOM_AREA_RATIO:
                        # Close-up zoom handoff: claimant walked very close to door!
                        closeup_handoff_triggered = True
                        wide_track_lost_streak = 0
                        sharpness, glare, quality = keyframe_selector.score_frame(orig_frame)
                        rel_t = frame_idx / total_frames if total_frames > 0 else 0.0
                        rec = {
                            "frame_idx": frame_idx,
                            "rel_t": rel_t,
                            "area_ratio": last_area_ratio,
                            "sharpness": sharpness,
                            "glare": glare,
                            "quality": quality,
                            "img": orig_frame.copy(),
                        }
                        candidate_pool[frame_idx] = rec
                    else:
                        wide_track_lost_streak += self.settings.VID_STRIDE
                        if wide_track_lost_streak > max_wide_lost_streak:
                            max_wide_lost_streak = wide_track_lost_streak

            # Select distinct canonical keyframes (front_bumper, side_body_panel, damage_closeup_primary)
            all_cands = list(candidate_pool.values())
            canonical_chosen = self._select_canonical_keyframes(
                all_cands, total_frames, plate_deferred, plate_anchor_frame, closeup_handoff_triggered
            )
            # ponytail: Curate adaptive trajectory keyframes (~1 frame per second of walkaround, bounded [8, 30])
            duration_sec = total_frames / max(1.0, fps)
            n_adaptive = max(8, min(30, int(duration_sec)))
            curated_chosen = self._curate_trajectory_keyframes(
                all_cands, total_frames, n_curated=n_adaptive
            )

            # Save canonical keyframes atomically
            saved_paths: Dict[str, str] = {}
            for view_name in ["front_bumper", "side_body_panel", "damage_closeup_primary"]:
                if view_name in canonical_chosen:
                    p = keyframe_selector.save_keyframe_atomically(
                        canonical_chosen[view_name]["img"], claim_id, view_name
                    )
                    saved_paths[view_name] = str(p)

            # Save curated keyframes atomically
            curated_paths: List[str] = []
            for i, cand in enumerate(curated_chosen, 1):
                p = keyframe_selector.save_keyframe_atomically(
                    cand["img"], claim_id, f"keyframe_{i:02d}"
                )
                curated_paths.append(str(p))

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
                f"late_plate={late_plate_verified}, keyframes_saved={list(saved_paths.keys())} ({duration_ms:.2f}ms)"
            )

            return TrackingAndKeyframeResult(
                is_persistent=is_persistent,
                target_track_id=target_track_id or 1,
                frames_tracked=frames_tracked,
                track_lost_count=max_wide_lost_streak,
                closeup_handoff_triggered=closeup_handoff_triggered,
                saved_keyframes=saved_paths,
                curated_keyframes=curated_paths,
                late_plate_verified=late_plate_verified,
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

