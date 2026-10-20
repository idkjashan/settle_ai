import hashlib
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np
import torch

from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.schemas import (
    FrameDualPredictions,
    RawMaskPrediction,
)
from app.domain.dual_mask_segmentation.taxonomy import (
    CARDD_CLASS_MAP,
    CARPARTS_CLASS_MAP,
    IGNORED_PART_CLASSES,
    validate_model_taxonomy,
)


class DualModelInferencer:
    """Executes batched FP16 inference across curated keyframes for both
    Model A (Carparts-Seg) and Model B (CarDD-Seg).
    """

    def __init__(
        self,
        carparts_model,
        cardd_model,
        settings: Optional[Stage2Settings] = None,
        validate_taxonomy: bool = True,
    ):
        if validate_taxonomy:
            validate_model_taxonomy(carparts_model, CARPARTS_CLASS_MAP, model_role="Carparts-Seg")
            validate_model_taxonomy(cardd_model, CARDD_CLASS_MAP, model_role="CarDD-Seg")

        self.carparts_model = carparts_model
        self.cardd_model = cardd_model
        self.settings = settings or Stage2Settings()

    @staticmethod
    def _compute_laplacian_720p(frame_bgr: np.ndarray) -> float:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        short_edge = min(h, w)
        if short_edge > 720:
            scale = 720.0 / float(short_edge)
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    @staticmethod
    def _extract_frame_idx(keyframe_key: str, fallback_idx: int) -> int:
        match = re.search(r"(\d+)$", keyframe_key)
        return int(match.group(1)) if match else fallback_idx

    def infer_keyframes(
        self, keyframe_paths: Dict[str, Path]
    ) -> Tuple[List[FrameDualPredictions], Dict[str, np.ndarray]]:
        loaded_frames_bgr: Dict[str, np.ndarray] = {}
        unique_hash_to_key: Dict[str, str] = {}
        ordered_keys: List[str] = []

        # 1. Load & deduplicate keyframes by SHA-1 digest so aliases aren't inferred twice
        for idx, (kf_key, kf_path) in enumerate(sorted(keyframe_paths.items())):
            kf_path = Path(kf_path)
            if not kf_path.exists():
                continue
            raw_bytes = kf_path.read_bytes()
            digest = hashlib.sha1(raw_bytes).hexdigest()
            img_arr = np.frombuffer(raw_bytes, dtype=np.uint8)
            frame_bgr = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
            if frame_bgr is None:
                continue
            loaded_frames_bgr[kf_key] = frame_bgr
            if digest not in unique_hash_to_key:
                unique_hash_to_key[digest] = kf_key
                ordered_keys.append(kf_key)

        predictions_out: List[FrameDualPredictions] = []
        batch_size = self.settings.gpu_batch_size
        use_half = self.settings.use_fp16_half and torch.cuda.is_available()

        # 2. Run batched inference on both YOLO11m-seg models
        for start_i in range(0, len(ordered_keys), batch_size):
            batch_keys = ordered_keys[start_i : start_i + batch_size]
            batch_imgs = [loaded_frames_bgr[k] for k in batch_keys]

            part_results = self.carparts_model.predict(
                source=batch_imgs,
                imgsz=self.settings.inference_imgsz,
                conf=self.settings.part_min_confidence,
                iou=0.50,
                half=use_half,
                retina_masks=True,
                verbose=False,
            )
            dmg_results = self.cardd_model.predict(
                source=batch_imgs,
                imgsz=self.settings.inference_imgsz,
                conf=self.settings.damage_min_confidence_global,
                iou=0.45,
                half=use_half,
                retina_masks=True,
                verbose=False,
            )

            for b_idx, kf_key in enumerate(batch_keys):
                frame_bgr = batch_imgs[b_idx]
                h_px, w_px = frame_bgr.shape[:2]
                sharpness = self._compute_laplacian_720p(frame_bgr)
                frame_idx = self._extract_frame_idx(kf_key, start_i + b_idx)

                p_preds = self._parse_ultralytics_result(
                    part_results[b_idx], CARPARTS_CLASS_MAP, w_px, h_px, filter_ignored=True
                )
                d_preds = self._parse_ultralytics_result(
                    dmg_results[b_idx], CARDD_CLASS_MAP, w_px, h_px, filter_ignored=False
                )

                predictions_out.append(
                    FrameDualPredictions(
                        keyframe_key=kf_key,
                        frame_path=keyframe_paths[kf_key],
                        frame_index=frame_idx,
                        width_px=w_px,
                        height_px=h_px,
                        laplacian_sharpness=round(sharpness, 2),
                        part_predictions=p_preds,
                        damage_predictions=d_preds,
                    )
                )

        return predictions_out, loaded_frames_bgr

    @staticmethod
    def _parse_ultralytics_result(
        res, class_map: Dict[int, str], width_px: int, height_px: int, filter_ignored: bool
    ) -> List[RawMaskPrediction]:
        extracted: List[RawMaskPrediction] = []
        if res.boxes is None or res.masks is None:
            return extracted

        boxes_xyxy = res.boxes.xyxy.cpu().numpy()
        confs = res.boxes.conf.cpu().numpy()
        cls_ids = res.boxes.cls.cpu().numpy().astype(int)
        polygons_xyn = res.masks.xyn

        for i in range(len(cls_ids)):
            cid = int(cls_ids[i])
            if cid not in class_map:
                continue
            cname = class_map[cid]
            if filter_ignored and cname in IGNORED_PART_CLASSES:
                continue
            xyn = polygons_xyn[i]
            if xyn is None or len(xyn) < 3:
                continue
            pts_px = np.column_stack((xyn[:, 0] * width_px, xyn[:, 1] * height_px))
            b = boxes_xyxy[i]
            bbox = (int(b[0]), int(b[1]), int(b[2]), int(b[3]))
            extracted.append(
                RawMaskPrediction(
                    class_id=cid,
                    class_name=cname,
                    confidence=round(float(confs[i]), 4),
                    bbox_xyxy=bbox,
                    polygon_xy_px=pts_px,
                )
            )
        return extracted
