#!/usr/bin/env python3
"""tools/model_training/prepare_dataset.py

Dataset acquisition, conversion, and generation utility for Auto-Settle AI
Stage 2 Dual-Mask Segmentation models:
1. Carparts-Seg (23 canonical part classes)
2. CarDD (6 canonical damage classes)

Features:
- Downloads official Ultralytics carparts-seg dataset archive.
- Converts COCO-format instance segmentation annotations (CarDD / Roboflow)
  to Ultralytics YOLO segmentation polygon format (normalized x1 y1 x2 y2 ...).
- Validates category labels and maps variants (e.g. 'glass shatter' -> 'glass_shatter').
- Generates reproducible mini synthetic datasets for offline smoke testing and CI verification.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import zipfile

import cv2
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("prepare_dataset")

# Canonical class maps matching app/domain/dual_mask_segmentation/taxonomy.py
CARPARTS_CLASSES: Dict[int, str] = {
    0: "back_bumper",
    1: "back_door",
    2: "back_glass",
    3: "back_left_door",
    4: "back_left_light",
    5: "back_light",
    6: "back_right_door",
    7: "back_right_light",
    8: "front_bumper",
    9: "front_door",
    10: "front_glass",
    11: "front_left_door",
    12: "front_left_light",
    13: "front_light",
    14: "front_right_door",
    15: "front_right_light",
    16: "hood",
    17: "left_mirror",
    18: "object",
    19: "right_mirror",
    20: "tailgate",
    21: "trunk",
    22: "wheel",
}

CARDD_CLASSES: Dict[int, str] = {
    0: "dent",
    1: "scratch",
    2: "crack",
    3: "glass_shatter",
    4: "lamp_broken",
    5: "tire_flat",
}

# Alias mapping for damage classes encountered in various COCO dumps
CARDD_NAME_ALIASES: Dict[str, int] = {
    "dent": 0,
    "scratch": 1,
    "scratches": 1,
    "crack": 2,
    "cracks": 2,
    "glass shatter": 3,
    "glass_shatter": 3,
    "glass-shatter": 3,
    "shattered_glass": 3,
    "lamp broken": 4,
    "lamp_broken": 4,
    "lamp-broken": 4,
    "broken_lamp": 4,
    "tire flat": 5,
    "tire_flat": 5,
    "tire-flat": 5,
    "flat_tire": 5,
}

ULTRALYTICS_CARPARTS_ZIP_URL = (
    "https://github.com/ultralytics/assets/releases/download/v0.0.0/carparts-seg.zip"
)


def download_and_extract_zip(url: str, dest_dir: Path) -> Path:
    """Downloads a zip archive and extracts it into dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / "dataset_download.zip"

    logger.info(f"Downloading dataset from {url} ...")
    urllib.request.urlretrieve(url, zip_path)
    logger.info(f"Extracting {zip_path.name} to {dest_dir} ...")

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)

    if zip_path.exists():
        zip_path.unlink()

    logger.info("Dataset download and extraction complete.")
    return dest_dir


def prepare_carparts_dataset(output_dir: Path) -> Path:
    """Prepares the official Carparts-Seg dataset."""
    output_dir = output_dir.resolve()
    target_data_dir = output_dir / "carparts-seg"

    # Check if already present
    if (target_data_dir / "images" / "train").exists():
        logger.info(f"Carparts dataset already exists at {target_data_dir}")
        return target_data_dir

    download_and_extract_zip(ULTRALYTICS_CARPARTS_ZIP_URL, output_dir)
    return target_data_dir if target_data_dir.exists() else output_dir


def convert_coco_json_to_yolo_seg(
    json_path: Path,
    images_dir: Path,
    output_labels_dir: Path,
    output_images_dir: Optional[Path] = None,
    category_mode: str = "cardd",
) -> Tuple[int, int]:
    """Converts a COCO instance segmentation JSON file to YOLO segmentation .txt format.

    Format per line:
    <class-id> x1 y1 x2 y2 x3 y3 ... (normalized coordinates in [0, 1])

    Returns:
        Tuple of (images_converted_count, annotations_converted_count)
    """
    if not json_path.exists():
        raise FileNotFoundError(f"COCO JSON file not found: {json_path}")

    logger.info(f"Loading COCO annotations from {json_path} ...")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Build image lookup: id -> {file_name, width, height}
    image_lookup: Dict[Any, Dict[str, Any]] = {}
    for img in data.get("images", []):
        image_lookup[img["id"]] = {
            "file_name": img["file_name"],
            "width": float(img["width"]),
            "height": float(img["height"]),
        }

    # Build category lookup: id -> canonical class index
    category_id_to_class_idx: Dict[int, int] = {}
    for cat in data.get("categories", []):
        raw_name = cat.get("name", "").strip().lower()
        cat_id = cat.get("id")
        if category_mode == "cardd":
            # Map by alias or 1-indexed fallback
            if raw_name in CARDD_NAME_ALIASES:
                category_id_to_class_idx[cat_id] = CARDD_NAME_ALIASES[raw_name]
            elif 1 <= cat_id <= 6:
                category_id_to_class_idx[cat_id] = cat_id - 1
            else:
                logger.warning(f"Unrecognized CarDD category: id={cat_id}, name='{raw_name}'")
        else:
            # Carparts mapping
            found = False
            for c_idx, c_name in CARPARTS_CLASSES.items():
                if c_name == raw_name or c_name.replace("_", "-") == raw_name:
                    category_id_to_class_idx[cat_id] = c_idx
                    found = True
                    break
            if not found:
                category_id_to_class_idx[cat_id] = cat_id

    # Group annotations by image_id
    annotations_by_img: Dict[Any, List[Dict[str, Any]]] = {}
    for ann in data.get("annotations", []):
        img_id = ann.get("image_id")
        annotations_by_img.setdefault(img_id, []).append(ann)

    output_labels_dir.mkdir(parents=True, exist_ok=True)
    if output_images_dir:
        output_images_dir.mkdir(parents=True, exist_ok=True)

    images_converted = 0
    total_polygons = 0

    for img_id, img_info in image_lookup.items():
        w = img_info["width"]
        h = img_info["height"]
        if w <= 0 or h <= 0:
            continue

        base_stem = Path(img_info["file_name"]).stem
        label_file = output_labels_dir / f"{base_stem}.txt"

        # Copy image if requested
        if output_images_dir and images_dir.exists():
            src_img = images_dir / img_info["file_name"]
            if not src_img.exists():
                src_img = images_dir / Path(img_info["file_name"]).name
            if src_img.exists():
                dest_img = output_images_dir / src_img.name
                if not dest_img.exists():
                    shutil.copy2(src_img, dest_img)

        anns = annotations_by_img.get(img_id, [])
        lines: List[str] = []

        for ann in anns:
            if ann.get("iscrowd", 0):
                continue

            raw_cat_id = ann.get("category_id")
            if raw_cat_id not in category_id_to_class_idx:
                continue
            class_idx = category_id_to_class_idx[raw_cat_id]

            # Process segmentation polygon
            segm = ann.get("segmentation")
            if not segm:
                continue

            # In COCO, segmentation is either a list of polygons or RLE dict
            if isinstance(segm, list):
                for poly in segm:
                    if len(poly) < 6:  # Need at least 3 (x, y) pairs
                        continue

                    normalized_coords: List[float] = []
                    for i in range(0, len(poly), 2):
                        px = poly[i]
                        py = poly[i + 1] if i + 1 < len(poly) else 0.0
                        nx = max(0.0, min(1.0, float(px) / w))
                        ny = max(0.0, min(1.0, float(py) / h))
                        normalized_coords.extend([nx, ny])

                    coord_str = " ".join(f"{c:.6f}" for c in normalized_coords)
                    lines.append(f"{class_idx} {coord_str}")
                    total_polygons += 1

        with open(label_file, "w", encoding="utf-8") as lf:
            for line in lines:
                lf.write(line + "\n")

        images_converted += 1

    logger.info(
        f"Conversion complete: {images_converted} images, {total_polygons} segmentation polygons saved to {output_labels_dir}"
    )
    return images_converted, total_polygons


def generate_synthetic_smoke_dataset(output_dir: Path, num_samples: int = 5) -> Tuple[Path, Path]:
    """Generates an end-to-end, hermetic mini dataset (5 train, 2 val) with valid
    carparts and cardd polygons for rapid CI smoke testing.

    Returns:
        Tuple of (carparts_yaml_path, cardd_yaml_path)
    """
    output_dir = output_dir.resolve()
    logger.info(f"Generating synthetic mini smoke dataset at {output_dir} ({num_samples} train samples) ...")

    for task_name, class_map in [("carparts", CARPARTS_CLASSES), ("cardd", CARDD_CLASSES)]:
        task_dir = output_dir / f"mini_{task_name}"
        task_dir.mkdir(parents=True, exist_ok=True)

        for split, count in [("train", num_samples), ("val", 2)]:
            img_dir = task_dir / "images" / split
            lbl_dir = task_dir / "labels" / split
            img_dir.mkdir(parents=True, exist_ok=True)
            lbl_dir.mkdir(parents=True, exist_ok=True)

            for i in range(count):
                img_name = f"sample_{split}_{i:03d}.jpg"
                lbl_name = f"sample_{split}_{i:03d}.txt"

                # Generate a 640x640 synthetic image with shapes
                width, height = 640, 640
                canvas = np.full((height, width, 3), 180 + (i * 10) % 60, dtype=np.uint8)

                label_lines: List[str] = []

                # Draw 2-3 geometric polygonal shapes representing classes
                num_shapes = 2 if task_name == "cardd" else 3
                for s in range(num_shapes):
                    class_idx = (i * num_shapes + s) % len(class_map)
                    # Skip 'object' (class 18) for carparts if possible
                    if task_name == "carparts" and class_idx == 18:
                        class_idx = 0

                    center_x = 150 + s * 160 + (i * 15) % 50
                    center_y = 200 + (s * 70) + (i * 20) % 100
                    radius = 50 + (s * 15)

                    # Create a polygon with 6 vertices
                    pts = []
                    norm_pts = []
                    for vertex in range(6):
                        angle = vertex * (2 * math.pi / 6)
                        vx = center_x + int(radius * math.cos(angle))
                        vy = center_y + int(radius * 0.7 * math.sin(angle))
                        vx = max(10, min(width - 10, vx))
                        vy = max(10, min(height - 10, vy))
                        pts.append([vx, vy])
                        norm_pts.extend([vx / width, vy / height])

                    # Draw polygon onto canvas
                    cv2.fillPoly(
                        canvas,
                        [np.array(pts, dtype=np.int32)],
                        color=((s * 70 + 50) % 255, (i * 80 + 30) % 255, 200),
                    )

                    coord_str = " ".join(f"{c:.6f}" for c in norm_pts)
                    label_lines.append(f"{class_idx} {coord_str}")

                # Save image and label
                cv2.imwrite(str(img_dir / img_name), canvas)
                with open(lbl_dir / lbl_name, "w", encoding="utf-8") as f:
                    for line in label_lines:
                        f.write(line + "\n")

        # Write dataset YAML
        yaml_path = task_dir / f"mini_{task_name}_seg.yaml"
        yaml_content = {
            "path": str(task_dir.as_posix()),
            "train": "images/train",
            "val": "images/val",
            "nc": len(class_map),
            "names": class_map,
        }
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(f"# Auto-generated smoke dataset config for {task_name}\n")
            f.write(f"path: {task_dir.as_posix()}\n")
            f.write("train: images/train\n")
            f.write("val: images/val\n")
            f.write(f"nc: {len(class_map)}\n")
            f.write("names:\n")
            for cid, cname in class_map.items():
                f.write(f"  {cid}: {cname}\n")

        logger.info(f"Generated {yaml_path}")

    carparts_yaml = output_dir / "mini_carparts" / "mini_carparts_seg.yaml"
    cardd_yaml = output_dir / "mini_cardd" / "mini_cardd_seg.yaml"
    return carparts_yaml, cardd_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-Settle AI Dataset Preparation & Conversion")
    parser.add_argument(
        "--task",
        choices=["carparts", "cardd", "smoke-dataset"],
        required=True,
        help="Task to perform: 'carparts' (download), 'cardd' (convert COCO), 'smoke-dataset' (generate mini)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data"),
        help="Destination directory for dataset",
    )
    parser.add_argument(
        "--coco-json",
        type=Path,
        default=None,
        help="Path to source COCO annotation JSON file (for 'cardd' task)",
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=None,
        help="Path to source images directory (for 'cardd' task)",
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=5,
        help="Number of train samples for synthetic smoke dataset",
    )

    args = parser.parse_args()

    if args.task == "carparts":
        out = prepare_carparts_dataset(args.output_dir)
        print(f"Carparts dataset prepared at: {out}")
    elif args.task == "cardd":
        if not args.coco_json:
            print("Error: --coco-json required for cardd conversion", file=sys.stderr)
            return 1
        lbl_dir = args.output_dir / "labels" / "train"
        img_out = args.output_dir / "images" / "train"
        convert_coco_json_to_yolo_seg(
            args.coco_json,
            args.images_dir or Path("."),
            lbl_dir,
            img_out,
            category_mode="cardd",
        )
    elif args.task == "smoke-dataset":
        cp_yaml, cd_yaml = generate_synthetic_smoke_dataset(args.output_dir, args.num_samples)
        print(f"Smoke datasets created successfully:\n  Carparts: {cp_yaml}\n  CarDD: {cd_yaml}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
