"""
occlusion_reid_tracker.py
-------------------------
Production occlusion-robust vehicle damage tracking orchestrator.
Combines ByteTrack spatial tracking with training-free intermediate C4 RoIAlign feature
re-identification and sliding-window temporal confirmation gating to eliminate track ID
switching and specular reflection flicker during 360° walkaround inspections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union
import cv2
import numpy as np
import torch
from ultralytics import YOLO

from app.domain.perception.tracking.feature_extractor import C4FeatureExtractor
from app.domain.perception.tracking.reid_gallery import ReidGallery
from app.domain.perception.tracking.temporal_confirmation_gate import TemporalConfirmationGate
from app.core.logging import logger


@dataclass
class TrackedDamage:
    """Represents an active tracked damage instance in a single frame."""
    final_id: int
    raw_track_id: int
    class_id: int
    class_name: str
    confidence: float
    bbox_xyxy: Tuple[int, int, int, int]
    polygon_xy_px: Optional[np.ndarray] = None
    frame_idx: int = 0
    is_confirmed: bool = False
    embedding: Optional[np.ndarray] = None


@dataclass
class TrackedDamageSummary:
    """Aggregated lifecycle summary of a persistent confirmed damage track across video."""
    final_id: int
    class_id: int
    class_name: str
    first_frame_idx: int
    last_frame_idx: int
    total_detections: int
    is_confirmed: bool
    best_confidence: float
    best_frame_idx: int
    best_bbox_xyxy: Tuple[int, int, int, int]
    best_polygon_xy_px: Optional[np.ndarray] = None
    best_frame_img: Optional[np.ndarray] = None
    trajectory_bboxes: List[Tuple[int, Tuple[int, int, int, int]]] = field(default_factory=list)


@dataclass
class VideoTrackingResult:
    """End-to-end tracking evaluation result across a video sequence."""
    video_path: str
    total_frames: int
    raw_unique_ids_count: int
    reid_unique_ids_count: int
    confirmed_unique_ids_count: int
    id_switch_reduction_pct: float
    confirmed_tracks: List[TrackedDamageSummary] = field(default_factory=list)
    all_tracks_summary: Dict[int, TrackedDamageSummary] = field(default_factory=dict)


class OcclusionReIDTracker:
    """Occlusion-Robust Damage Tracker with C4 RoIAlign Re-ID and Temporal Confirmation."""

    def __init__(
        self,
        yolo_model: Optional[Union[YOLO, str, Path]] = None,
        weights_path: Optional[Union[str, Path]] = None,
        cosine_thresh: float = 0.60,
        gallery_max_gap: int = 150,
        temporal_min_hits: int = 3,
        temporal_window_size: int = 20,
        layer_idx: int = 6,
        conf_threshold: float = 0.15,
        device: Optional[str] = None,
    ):
        self.conf_threshold = conf_threshold
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        # Load or bind YOLO model
        if isinstance(yolo_model, YOLO):
            self.model = yolo_model
        elif yolo_model is not None:
            self.model = YOLO(str(yolo_model))
        elif weights_path is not None:
            self.model = YOLO(str(weights_path))
        else:
            default_weights = Path("weights/cardd-yolov8s-seg.pt")
            if default_weights.exists():
                self.model = YOLO(str(default_weights))
            else:
                self.model = None

        if self.model is not None and hasattr(self.model, "to") and self.device == "cuda":
            try:
                self.model.to("cuda")
            except Exception as e:
                logger.warning(f"Failed to move model to CUDA: {e}")

        # Initialize C4 feature extractor hooked to layer 6
        self.feature_extractor = (
            C4FeatureExtractor(model=self.model, layer_idx=layer_idx)
            if self.model is not None
            else None
        )

        # Initialize ReID Gallery & Temporal Gate
        self.gallery = ReidGallery(
            cosine_thresh=cosine_thresh,
            max_gap=gallery_max_gap,
            max_samples_per_track=5,
        )
        self.temporal_gate = TemporalConfirmationGate(
            min_hits=temporal_min_hits,
            window_size=temporal_window_size,
        )

        # State tracking structures
        self._raw_to_final_id: Dict[int, int] = {}
        self._appearance_history: Dict[int, List[np.ndarray]] = {}
        self._active_final_ids_prev: Set[int] = set()
        self._all_raw_ids_seen: Set[int] = set()
        self._all_final_ids_seen: Set[int] = set()
        self._track_summaries: Dict[int, TrackedDamageSummary] = {}

    def reset(self) -> None:
        """Resets all tracker internal states, gallery, and temporal histories."""
        self.gallery.clear()
        self.temporal_gate.clear()
        self._raw_to_final_id.clear()
        self._appearance_history.clear()
        self._active_final_ids_prev.clear()
        self._all_raw_ids_seen.clear()
        self._all_final_ids_seen.clear()
        self._track_summaries.clear()

        # Reset ByteTrack internal Kalman filter state if accessible
        if self.model is not None:
            try:
                if hasattr(self.model, "predictor") and self.model.predictor:
                    if hasattr(self.model.predictor, "trackers"):
                        for t in self.model.predictor.trackers:
                            if hasattr(t, "reset"):
                                t.reset()
            except Exception as e:
                logger.debug(f"ByteTrack state reset pass: {e}")

    def track_frame(
        self,
        frame_bgr: np.ndarray,
        frame_idx: int,
        conf: Optional[float] = None,
    ) -> List[TrackedDamage]:
        """Tracks damages in a single frame, re-identifying lost tracks and applying temporal gating.

        Args:
            frame_bgr: BGR input image array.
            frame_idx: Current frame index (1-based or 0-based).
            conf: Optional confidence threshold override.

        Returns:
            List of TrackedDamage objects detected in the current frame.
        """
        if self.model is None:
            raise RuntimeError("YOLO model is not initialized on tracker.")

        det_conf = conf or self.conf_threshold
        h_img, w_img = frame_bgr.shape[:2]

        # Run ByteTrack inference
        results = self.model.track(
            source=frame_bgr,
            persist=True,
            tracker="bytetrack.yaml",
            conf=det_conf,
            verbose=False,
        )

        if not results or len(results) == 0:
            self._handle_empty_frame(frame_idx)
            return []

        res = results[0]
        boxes_obj = res.boxes
        if boxes_obj is None or len(boxes_obj) == 0:
            self._handle_empty_frame(frame_idx)
            return []

        # Extract detection arrays
        boxes_xyxy = boxes_obj.xyxy.cpu().numpy().astype(int)
        confs = boxes_obj.conf.cpu().numpy().astype(float)
        cls_ids = boxes_obj.cls.cpu().numpy().astype(int)
        raw_ids = (
            boxes_obj.id.int().cpu().numpy().tolist()
            if boxes_obj.id is not None
            else [-(i + 1) for i in range(len(boxes_xyxy))]
        )

        # Polygons extraction (if segmentation model)
        polygons = []
        if res.masks is not None and res.masks.xyn is not None:
            for xyn in res.masks.xyn:
                if xyn is not None and len(xyn) >= 3:
                    pts = np.column_stack((xyn[:, 0] * w_img, xyn[:, 1] * h_img))
                    polygons.append(pts)
                else:
                    polygons.append(None)
        else:
            polygons = [None] * len(boxes_xyxy)

        # Extract C4 RoIAlign embeddings for all detection boxes in this frame
        if self.feature_extractor is not None and self.feature_extractor.captured_feature_map is not None:
            embeds = self.feature_extractor.extract_roi_embeddings(
                boxes_xyxy, img_shape=(h_img, w_img)
            )
        else:
            # Fallback for detectors without feature hook
            embeds = np.zeros((len(boxes_xyxy), 128), dtype=np.float32)

        # Process Re-ID and ID association
        current_tracked_damages = self._associate_and_reid(
            frame_bgr=frame_bgr,
            frame_idx=frame_idx,
            boxes_xyxy=boxes_xyxy,
            confs=confs,
            cls_ids=cls_ids,
            raw_ids=raw_ids,
            polygons=polygons,
            embeds=embeds,
        )

        return current_tracked_damages

    def _associate_and_reid(
        self,
        frame_bgr: np.ndarray,
        frame_idx: int,
        boxes_xyxy: np.ndarray,
        confs: np.ndarray,
        cls_ids: np.ndarray,
        raw_ids: List[int],
        polygons: List[Optional[np.ndarray]],
        embeds: np.ndarray,
    ) -> List[TrackedDamage]:
        """Core Re-ID Hungarian association and lifecycle state transition logic."""
        class_names = getattr(self.model, "names", {})
        num_dets = len(raw_ids)

        # Distinguish between active tracks vs newly spawned tracks
        newborn_indices: List[int] = []
        assigned_final_ids: List[Optional[int]] = [None] * num_dets

        for i, raw_id in enumerate(raw_ids):
            self._all_raw_ids_seen.add(raw_id)
            if raw_id in self._raw_to_final_id:
                # Track was already assigned a final persistent ID
                assigned_final_ids[i] = self._raw_to_final_id[raw_id]
            else:
                # Newborn track: ByteTrack just spawned a new raw ID
                newborn_indices.append(i)

        # Re-ID newborn tracks against the lost gallery
        if newborn_indices and self.gallery.bank_size > 0:
            candidate_embeds = embeds[newborn_indices]
            candidate_raw_ids = [raw_ids[idx] for idx in newborn_indices]
            reid_matches = self.gallery.match_newborns(
                candidate_embeds, candidate_ids=candidate_raw_ids, frame_id=frame_idx
            )
            for cand_pos, matched_fid in enumerate(reid_matches):
                orig_idx = newborn_indices[cand_pos]
                raw_id = raw_ids[orig_idx]
                if matched_fid is not None:
                    # Match found! Re-use the historic lost track ID
                    assigned_final_ids[orig_idx] = matched_fid
                    self._raw_to_final_id[raw_id] = matched_fid
                else:
                    # No gallery match: allocate persistent ID as raw_id
                    assigned_final_ids[orig_idx] = raw_id
                    self._raw_to_final_id[raw_id] = raw_id
        else:
            # No gallery or no newborns
            for orig_idx in newborn_indices:
                raw_id = raw_ids[orig_idx]
                assigned_final_ids[orig_idx] = raw_id
                self._raw_to_final_id[raw_id] = raw_id

        # Update appearance histories and active tracks set
        current_active_final_ids: Set[int] = set()
        current_tracked_damages: List[TrackedDamage] = []

        for i in range(num_dets):
            final_id = assigned_final_ids[i]
            current_active_final_ids.add(final_id)
            self._all_final_ids_seen.add(final_id)

            # Store / update appearance sample
            emb = embeds[i]
            if final_id not in self._appearance_history:
                self._appearance_history[final_id] = []
            self._appearance_history[final_id].append(emb)
            if len(self._appearance_history[final_id]) > 5:
                self._appearance_history[final_id].pop(0)

        # Detect tracks that became lost in this frame (were active previously, but missing now)
        lost_final_ids = self._active_final_ids_prev - current_active_final_ids
        for lost_fid in lost_final_ids:
            if lost_fid in self._appearance_history and len(self._appearance_history[lost_fid]) > 0:
                history_arr = np.array(self._appearance_history[lost_fid])
                self.gallery.bury(lost_fid, embeds=history_arr, frame_id=frame_idx)

        # Age and prune the gallery
        self.gallery.age_and_prune(frame_idx)
        self._active_final_ids_prev = current_active_final_ids

        # Update Temporal Confirmation Gate
        self.temporal_gate.update(frame_idx, list(current_active_final_ids))

        # Build frame results and update lifetime track summaries
        for i in range(num_dets):
            final_id = assigned_final_ids[i]
            raw_id = raw_ids[i]
            cid = int(cls_ids[i])
            cname = class_names.get(cid, f"damage_{cid}")
            conf_val = float(confs[i])
            bbox = (int(boxes_xyxy[i, 0]), int(boxes_xyxy[i, 1]), int(boxes_xyxy[i, 2]), int(boxes_xyxy[i, 3]))
            poly = polygons[i]
            is_confirmed = self.temporal_gate.is_confirmed(final_id)

            damage_item = TrackedDamage(
                final_id=final_id,
                raw_track_id=raw_id,
                class_id=cid,
                class_name=cname,
                confidence=conf_val,
                bbox_xyxy=bbox,
                polygon_xy_px=poly,
                frame_idx=frame_idx,
                is_confirmed=is_confirmed,
                embedding=embeds[i],
            )
            current_tracked_damages.append(damage_item)

            # Update aggregated summary
            self._update_track_summary(
                damage_item=damage_item,
                frame_bgr=frame_bgr,
                frame_idx=frame_idx,
            )

        return current_tracked_damages

    def _handle_empty_frame(self, frame_idx: int) -> None:
        """Handles a frame where no damage detections occurred."""
        # All previously active tracks are now lost
        for lost_fid in self._active_final_ids_prev:
            if lost_fid in self._appearance_history and len(self._appearance_history[lost_fid]) > 0:
                history_arr = np.array(self._appearance_history[lost_fid])
                self.gallery.bury(lost_fid, embeds=history_arr, frame_id=frame_idx)

        self.gallery.age_and_prune(frame_idx)
        self._active_final_ids_prev.clear()
        self.temporal_gate.update(frame_idx, [])

    def _update_track_summary(
        self,
        damage_item: TrackedDamage,
        frame_bgr: np.ndarray,
        frame_idx: int,
    ) -> None:
        """Maintains the lifetime summary for each persistent damage track."""
        fid = damage_item.final_id
        if fid not in self._track_summaries:
            self._track_summaries[fid] = TrackedDamageSummary(
                final_id=fid,
                class_id=damage_item.class_id,
                class_name=damage_item.class_name,
                first_frame_idx=frame_idx,
                last_frame_idx=frame_idx,
                total_detections=1,
                is_confirmed=damage_item.is_confirmed,
                best_confidence=damage_item.confidence,
                best_frame_idx=frame_idx,
                best_bbox_xyxy=damage_item.bbox_xyxy,
                best_polygon_xy_px=damage_item.polygon_xy_px,
                best_frame_img=frame_bgr.copy(),
                trajectory_bboxes=[(frame_idx, damage_item.bbox_xyxy)],
            )
        else:
            summ = self._track_summaries[fid]
            summ.last_frame_idx = frame_idx
            summ.total_detections += 1
            summ.is_confirmed = summ.is_confirmed or damage_item.is_confirmed
            summ.trajectory_bboxes.append((frame_idx, damage_item.bbox_xyxy))

            # Update best frame if higher confidence
            if damage_item.confidence > summ.best_confidence:
                summ.best_confidence = damage_item.confidence
                summ.best_frame_idx = frame_idx
                summ.best_bbox_xyxy = damage_item.bbox_xyxy
                summ.best_polygon_xy_px = damage_item.polygon_xy_px
                summ.best_frame_img = frame_bgr.copy()

    def track_video(
        self,
        video_path: Union[str, Path],
        conf: Optional[float] = None,
        vid_stride: int = 1,
        max_frames: Optional[int] = None,
    ) -> VideoTrackingResult:
        """Processes a full video file, performing continuous Re-ID damage tracking.

        Args:
            video_path: Path to MP4/video file.
            conf: Confidence threshold for detector.
            vid_stride: Frame stride (default 1 for full sequential tracking).
            max_frames: Optional cap on total frames processed.

        Returns:
            VideoTrackingResult with confirmed damage tracks and ID switch metrics.
        """
        self.reset()
        vpath = Path(video_path)
        if not vpath.exists():
            raise FileNotFoundError(f"Video file not found at {video_path}")

        cap = cv2.VideoCapture(str(vpath))
        if not cap.isOpened():
            raise RuntimeError(f"OpenCV failed to open video {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_idx = 0
        processed_count = 0

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frame_idx += 1

                if (frame_idx - 1) % vid_stride != 0:
                    continue

                processed_count += 1
                self.track_frame(frame, frame_idx=frame_idx, conf=conf)

                if max_frames is not None and processed_count >= max_frames:
                    break
        finally:
            cap.release()

        # Calculate metrics
        raw_count = len(self._all_raw_ids_seen)
        reid_count = len(self._all_final_ids_seen)
        confirmed_ids = self.temporal_gate.get_confirmed_ids()

        confirmed_summaries = [
            summ for fid, summ in self._track_summaries.items()
            if fid in confirmed_ids or summ.is_confirmed
        ]

        reduction_pct = (
            ((raw_count - reid_count) / float(raw_count) * 100.0)
            if raw_count > 0
            else 0.0
        )

        logger.info(
            f"OcclusionReIDTracker on {vpath.name}: {processed_count} frames, "
            f"raw_ids={raw_count} -> reid_ids={reid_count} -> confirmed={len(confirmed_summaries)} "
            f"(reduction={reduction_pct:.1f}%)"
        )

        return VideoTrackingResult(
            video_path=str(vpath),
            total_frames=processed_count,
            raw_unique_ids_count=raw_count,
            reid_unique_ids_count=reid_count,
            confirmed_unique_ids_count=len(confirmed_summaries),
            id_switch_reduction_pct=round(reduction_pct, 2),
            confirmed_tracks=confirmed_summaries,
            all_tracks_summary=self._track_summaries,
        )
