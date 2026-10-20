#!/usr/bin/env python3
"""tools/model_training/train_yolo_seg.py

Production-grade training and fine-tuning engine for Auto-Settle AI
Stage 2 Dual-Mask Segmentation models.

Optimized for NVIDIA GeForce RTX 4060 Laptop GPU (8GB VRAM) and CUDA 12.4+:
- Mixed Precision (AMP: fp16) enabled for Tensor Core acceleration.
- Batch size defaulted to 8 (YOLO11m) or 16 (YOLO11n/s) to prevent VRAM spikes.
- Worker count = 4 with memory pinning.
- RAM/disk caching enabled for maximum throughput.
- Automatic post-training validation against Stage 2 canonical taxonomy.
- Automatic checkpoint verification and export to `weights/`.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, Optional

import torch
from ultralytics import YOLO

# Add repository root to path for taxonomy validation
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.domain.dual_mask_segmentation.taxonomy import (
    CARDD_CLASS_MAP,
    CARPARTS_CLASS_MAP,
    validate_model_taxonomy,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("train_yolo_seg")


def compute_file_sha256(filepath: Path) -> str:
    """Computes the SHA-256 checksum of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192 * 1024):
            h.update(chunk)
    return h.hexdigest()


def inspect_hardware_and_vram() -> Dict[str, Any]:
    """Inspects CUDA device capabilities and VRAM headroom."""
    info: Dict[str, Any] = {
        "cuda_available": torch.cuda.is_available(),
        "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        "device_name": "CPU",
        "total_vram_gb": 0.0,
        "recommended_batch_m": 8,
        "recommended_batch_n": 16,
    }

    if info["cuda_available"]:
        props = torch.cuda.get_device_properties(0)
        info["device_name"] = props.name
        info["total_vram_gb"] = round(props.total_memory / (1024**3), 2)
        logger.info(
            f"Detected GPU: {info['device_name']} ({info['total_vram_gb']} GB VRAM, "
            f"CUDA capability {props.major}.{props.minor})"
        )
        if info["total_vram_gb"] < 10.0:
            logger.info("8GB VRAM constraint detected: using recommended batch=8 for medium models, batch=16 for nano/small.")
            info["recommended_batch_m"] = 8
            info["recommended_batch_n"] = 16
        else:
            info["recommended_batch_m"] = 16
            info["recommended_batch_n"] = 32
    else:
        logger.warning("CUDA not detected. Training will run on CPU (very slow!).")

    return info


def train_segmentation_model(
    task: str,
    data_yaml: Path,
    base_model: str = "weights/yolo11m-seg.pt",
    output_weights: Optional[Path] = None,
    epochs: int = 50,
    batch_size: Optional[int] = None,
    imgsz: int = 640,
    device: Optional[str] = None,
    workers: int = 4,
    patience: int = 15,
    amp: bool = True,
    cache: bool = True,
    project_dir: Path = Path("runs/segment"),
    run_name: Optional[str] = None,
) -> Path:
    """Trains a YOLO segmentation model and validates its taxonomy."""
    task = task.lower().strip()
    if task not in ("cardd", "carparts"):
        raise ValueError(f"Task must be 'cardd' or 'carparts', got '{task}'")

    expected_taxonomy = CARDD_CLASS_MAP if task == "cardd" else CARPARTS_CLASS_MAP
    role_name = "CarDD-Seg" if task == "cardd" else "Carparts-Seg"

    if not data_yaml.exists():
        raise FileNotFoundError(f"Dataset YAML config not found at: {data_yaml}")

    hw = inspect_hardware_and_vram()

    # Determine batch size
    if batch_size is None:
        is_nano_or_small = any(k in str(base_model).lower() for k in ["yolov8n", "yolo11n", "yolov8s", "yolo11s"])
        batch_size = hw["recommended_batch_n"] if is_nano_or_small else hw["recommended_batch_m"]

    # Determine device
    if device is None:
        device = "0" if hw["cuda_available"] else "cpu"

    if run_name is None:
        run_name = f"{task}_training"

    # Default output weights path
    if output_weights is None:
        output_weights = Path(f"weights/yolo11m-{task}-seg.pt")

    logger.info(
        f"Starting training:\n"
        f"  Task:            {task} ({role_name})\n"
        f"  Base Checkpoint: {base_model}\n"
        f"  Dataset Config:  {data_yaml}\n"
        f"  Epochs:          {epochs}\n"
        f"  Batch Size:      {batch_size}\n"
        f"  Image Size:      {imgsz}\n"
        f"  Device:          {device}\n"
        f"  Mixed Precision: {amp}\n"
        f"  Workers:         {workers}\n"
        f"  Patience:        {patience}\n"
        f"  Target Output:   {output_weights}\n"
    )

    # Initialize Ultralytics YOLO model
    model = YOLO(base_model)

    # Execute training
    results = model.train(
        data=str(data_yaml),
        epochs=epochs,
        batch=batch_size,
        imgsz=imgsz,
        device=device,
        amp=amp,
        cache=cache,
        workers=workers,
        patience=patience,
        project=str(project_dir),
        name=run_name,
        save=True,
        exist_ok=True,
        plots=True,
        val=True,
    )

    # Locate best.pt from trainer save_dir or project directory
    save_dir = Path(getattr(model.trainer, "save_dir", project_dir / run_name))
    candidate_weights = [
        save_dir / "weights" / "best.pt",
        save_dir / "weights" / "last.pt",
        project_dir / run_name / "weights" / "best.pt",
        project_dir / run_name / "weights" / "last.pt",
        project_dir / "runs" / "segment" / run_name / "weights" / "best.pt",
        project_dir / "runs" / "segment" / run_name / "weights" / "last.pt",
    ]

    best_weights_path = None
    for cand in candidate_weights:
        if cand.exists():
            best_weights_path = cand
            break

    if best_weights_path is None:
        raise RuntimeError(f"Training completed but neither best.pt nor last.pt was found in {save_dir / 'weights'}")

    logger.info(f"Training run finished. Evaluating saved weights: {best_weights_path}")

    # Load trained model to validate taxonomy strictly
    trained_model = YOLO(str(best_weights_path))
    logger.info(f"Trained model class count: {len(trained_model.names)}")
    logger.info(f"Validating model against canonical taxonomy ({role_name}) ...")

    validate_model_taxonomy(trained_model, expected_taxonomy, model_role=role_name)
    logger.info(f"✅ Taxonomy validation PASSED: Model strictly complies with {role_name} taxonomy!")

    # Copy to target destination
    output_weights.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best_weights_path, output_weights)

    sha256_hash = compute_file_sha256(output_weights)
    size_mb = round(output_weights.stat().st_size / (1024**2), 2)

    logger.info(
        f"========================================================\n"
        f"🏆 MODEL TRAINING & VERIFICATION COMPLETE\n"
        f"  Target File:    {output_weights}\n"
        f"  File Size:      {size_mb} MB\n"
        f"  SHA-256:        {sha256_hash}\n"
        f"  Classes ({len(expected_taxonomy)}):    {list(expected_taxonomy.values())[:6]} ...\n"
        f"========================================================"
    )

    return output_weights


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-Settle AI YOLO Segmentation Training Engine")
    parser.add_argument(
        "--task",
        choices=["cardd", "carparts"],
        required=True,
        help="Target model task: 'cardd' (damage) or 'carparts' (components)",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="Path to dataset YAML config (defaults to tools/model_training/{task}_seg.yaml)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="weights/yolo11m-seg.pt",
        help="Initial model checkpoint (e.g. weights/yolo11m-seg.pt, yolo11n-seg.pt, or yolov8s-seg.pt)",
    )
    parser.add_argument(
        "--output-weights",
        type=Path,
        default=None,
        help="Destination path for final verified model weights (defaults to weights/yolo11m-{task}-seg.pt)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=50,
        help="Number of training epochs (use 1 for smoke tests)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=None,
        help="Batch size (defaults to 8 for medium models on 8GB VRAM, 16 for nano/small)",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Image resolution (default 640)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="CUDA device index ('0') or 'cpu' (default: auto)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Dataloader workers (default: 4)",
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=15,
        help="Early stopping patience epochs (default: 15)",
    )
    parser.add_argument(
        "--no-amp",
        action="store_true",
        help="Disable Automatic Mixed Precision (AMP)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable dataset RAM caching",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default=None,
        help="Name for this training run directory",
    )

    args = parser.parse_args()

    default_data_yaml = REPO_ROOT / f"tools/model_training/{args.task}_seg.yaml"
    data_yaml = args.data or default_data_yaml

    # If base_model doesn't exist locally, check if it's standard ultralytics weight name
    base_model = args.model
    if not Path(base_model).exists():
        if base_model.startswith("weights/"):
            # Check if basename exists or can be downloaded
            fallback_basename = Path(base_model).name
            logger.info(f"Local {base_model} not found, using base {fallback_basename}")
            base_model = fallback_basename

    try:
        train_segmentation_model(
            task=args.task,
            data_yaml=data_yaml,
            base_model=base_model,
            output_weights=args.output_weights,
            epochs=args.epochs,
            batch_size=args.batch,
            imgsz=args.imgsz,
            device=args.device,
            workers=args.workers,
            patience=args.patience,
            amp=not args.no_amp,
            cache=not args.no_cache,
            run_name=args.run_name,
        )
        return 0
    except Exception as err:
        logger.error(f"Training failed: {err}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
