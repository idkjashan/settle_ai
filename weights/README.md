# Model Weights Directory

This directory stores deep learning model weights used by Auto-Settle AI:

- `yolo11m-seg.pt`: Ultralytics YOLO11 medium instance segmentation model (used for vehicle mask extraction and ByteTrack in Stage 1, and fine-tuned for car parts/damage in Stage 2).
- `yolov8n.pt`: Nano model used for rapid CPU bounding box fallbacks.

## Automatic Download

The weights are downloaded automatically on first run via Ultralytics:
```python
from ultralytics import YOLO
model = YOLO("weights/yolo11m-seg.pt")
```
Alternatively, download directly:
```bash
mkdir -p weights
curl -L -o weights/yolo11m-seg.pt https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m-seg.pt
```
