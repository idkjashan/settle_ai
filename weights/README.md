# Model Weights Directory

This directory stores deep learning model weights used by Auto-Settle AI across all perception stages:

| Model File | Architecture | Classes | Role in Pipeline | Hardware Target |
| :--- | :--- | :---: | :--- | :--- |
| `cardd-yolov8s-seg.pt` | YOLOv8-small Segmentation | 6 | **Stage 2 Damage Segmentation**: Detects `dent`, `scratch`, `crack`, `puncture`, `glass_shatter`, `lamp_broken`. | GPU FP16 (CUDA) |
| `carparts-yolo11n-seg.pt` | YOLO11-nano Segmentation | 23 | **Stage 2 Part Segmentation**: Identifies 23 canonical exterior vehicle body panels and lights. | GPU FP16 (CUDA) |
| `yolo11m-seg.pt` | YOLO11-medium Segmentation | 80 (COCO) | **Stage 1 Vehicle Identity**: Vehicle bounding box extraction, ByteTrack tracking, and ANPR plate ROI cropping. | GPU FP16 (CUDA) |
| `yolov8n.pt` | YOLOv8-nano Detection | 80 (COCO) | **Fast Fallback**: Lightweight CPU bounding box fallback. | CPU / Edge |

---

## Model Sourcing & Provenance

1. **`cardd-yolov8s-seg.pt`**:
   - Checkpoint trained on the **CarDD (Car Damage Dataset)** comprising 4,000 high-resolution damage annotations across 6 fine-grained damage classes.
2. **`carparts-yolo11n-seg.pt`**:
   - Checkpoint trained on the **Carparts-Seg** exterior vehicle component dataset with 23 exterior classes.
3. **`yolo11m-seg.pt`**:
   - Upstream base model from Ultralytics release assets (`v8.3.0`).

---

## Local Training & Fine-Tuning Pipeline

To retrain or fine-tune models locally on an NVIDIA RTX 4060 GPU or compatible CUDA device, use the automated toolchain:

```bash
# 1. Run a 1-epoch GPU verification smoke test on synthetic mini-dataset
./scripts/train_wsl.sh --smoke --task cardd

# 2. Launch full training on CarDD dataset
./scripts/train_wsl.sh --task cardd --epochs 50 --batch 8

# 3. For native Windows host without WSL
scripts\train_windows.bat --smoke --task cardd
```
