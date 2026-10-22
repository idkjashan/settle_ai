"""
feature_extractor.py
--------------------
Extracts training-free intermediate convolutional representations (C4 / backbone layer)
from vehicle damage detectors (e.g. YOLOv8s-seg / YOLO11m-seg) and pools them via RoIAlign
into normalized d-dimensional embedding vectors for appearance re-identification.
"""

from __future__ import annotations

from typing import List, Optional, Tuple, Union
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision.ops import roi_align


class C4FeatureExtractor:
    """Attaches a forward hook to the detector's C4 / P4 backbone layer (stride 16)
    and provides RoIAlign feature pooling for candidate bounding boxes.
    """

    def __init__(
        self,
        model: Optional[Union[nn.Module, object]] = None,
        layer_idx: int = 6,
        spatial_stride: int = 16,
        roi_output_size: Tuple[int, int] = (7, 7),
    ):
        self.layer_idx = layer_idx
        self.spatial_scale = 1.0 / float(spatial_stride)
        self.roi_output_size = roi_output_size
        self._hook_handle = None
        self._captured_feature_map: Optional[torch.Tensor] = None

        if model is not None:
            self.attach_hook(model)

    def attach_hook(self, model: Union[nn.Module, object]) -> None:
        """Attaches a PyTorch forward hook to the specified layer of the detector model."""
        self.remove_hook()

        # Handle Ultralytics YOLO wrapper (model.model.model) or raw nn.Module
        target_module = None
        if hasattr(model, "model") and hasattr(model.model, "model"):
            submodules = model.model.model
            if isinstance(submodules, (nn.Sequential, nn.ModuleList)) and len(submodules) > self.layer_idx:
                target_module = submodules[self.layer_idx]
            else:
                target_module = getattr(model.model, "model", None)
        elif hasattr(model, "model") and isinstance(model.model, nn.Module):
            if hasattr(model.model, "layers") and len(model.model.layers) > self.layer_idx:
                target_module = model.model.layers[self.layer_idx]
            else:
                target_module = model.model
        elif isinstance(model, nn.Module):
            named_mods = list(model.children())
            if len(named_mods) > self.layer_idx:
                target_module = named_mods[self.layer_idx]
            else:
                target_module = model

        if target_module is None:
            raise ValueError(f"Could not locate layer index {self.layer_idx} on model {type(model)}")

        def _hook(module, inputs, output):
            if isinstance(output, (list, tuple)):
                output = output[-1]
            self._captured_feature_map = output

        self._hook_handle = target_module.register_forward_hook(_hook)

    def remove_hook(self) -> None:
        """Removes the forward hook if attached."""
        if self._hook_handle is not None:
            self._hook_handle.remove()
            self._hook_handle = None

    @property
    def captured_feature_map(self) -> Optional[torch.Tensor]:
        return self._captured_feature_map

    @captured_feature_map.setter
    def captured_feature_map(self, feat: Optional[torch.Tensor]) -> None:
        self._captured_feature_map = feat

    def extract_roi_embeddings(
        self,
        boxes_xyxy: Union[np.ndarray, torch.Tensor, List[List[float]]],
        feature_map: Optional[torch.Tensor] = None,
        img_shape: Optional[Tuple[int, int]] = None,
    ) -> np.ndarray:
        """Extracts normalized d-dimensional embedding vectors for bounding boxes using RoIAlign.

        Args:
            boxes_xyxy: (N, 4) bounding boxes in [x1, y1, x2, y2] coordinates.
            feature_map: Optional (B, C, H_feat, W_feat) tensor. Defaults to captured_feature_map.
            img_shape: Optional (H, W) of the input image for coordinate scaling if needed.

        Returns:
            (N, C) numpy array of unit L2-normalized feature embeddings.
        """
        feat = feature_map if feature_map is not None else self._captured_feature_map
        if feat is None:
            raise RuntimeError("No feature map available. Ensure model forward pass was run or pass feature_map.")

        if isinstance(boxes_xyxy, (list, tuple)):
            if len(boxes_xyxy) == 0:
                c_dim = feat.shape[1]
                return np.zeros((0, c_dim), dtype=np.float32)
            boxes_tensor = torch.tensor(boxes_xyxy, dtype=torch.float32, device=feat.device)
        elif isinstance(boxes_xyxy, np.ndarray):
            if len(boxes_xyxy) == 0:
                c_dim = feat.shape[1]
                return np.zeros((0, c_dim), dtype=np.float32)
            boxes_tensor = torch.from_numpy(boxes_xyxy).float().to(feat.device)
        elif isinstance(boxes_xyxy, torch.Tensor):
            if boxes_xyxy.numel() == 0:
                c_dim = feat.shape[1]
                return np.zeros((0, c_dim), dtype=np.float32)
            boxes_tensor = boxes_xyxy.float().to(feat.device)
        else:
            raise TypeError(f"Unsupported boxes type: {type(boxes_xyxy)}")

        # Ensure boxes shape is (N, 4)
        if boxes_tensor.ndim == 1:
            boxes_tensor = boxes_tensor.unsqueeze(0)

        # Scale coordinates if image shape and feature map shape indicate discrepancy
        if img_shape is not None:
            h_img, w_img = img_shape
            _, _, h_feat, w_feat = feat.shape
            scale_x = (w_feat * (1.0 / self.spatial_scale)) / float(w_img)
            scale_y = (h_feat * (1.0 / self.spatial_scale)) / float(h_img)
            # If input image was resized before model forward
            if abs(scale_x - 1.0) > 1e-3 or abs(scale_y - 1.0) > 1e-3:
                boxes_tensor = boxes_tensor.clone()
                boxes_tensor[:, [0, 2]] *= scale_x
                boxes_tensor[:, [1, 3]] *= scale_y

        # Prepare RoI list for torchvision roi_align: list of (N, 4) per batch item or (N, 5) with batch index
        # When single image feature map (B=1):
        if feat.ndim == 3:
            feat = feat.unsqueeze(0)

        with torch.no_grad():
            # RoIAlign expects boxes as Tensor[K, 5] or List[Tensor[L, 4]]
            rois = [boxes_tensor]
            pooled_rois = roi_align(
                feat,
                rois,
                output_size=self.roi_output_size,
                spatial_scale=self.spatial_scale,
                sampling_ratio=2,
                aligned=True,
            )  # (N, C, 7, 7)

            # Global average pooling over spatial dimensions (7, 7)
            pooled_vectors = pooled_rois.mean(dim=[2, 3])  # (N, C)

            # L2 unit normalization
            normalized_embeds = F.normalize(pooled_vectors, p=2, dim=-1, eps=1e-9)

        return normalized_embeds.cpu().numpy().astype(np.float32)

    def __del__(self):
        self.remove_hook()
