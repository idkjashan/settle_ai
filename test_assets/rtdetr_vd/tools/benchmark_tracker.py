#!/usr/bin/env python3
"""
Runs ByteTrack tracking on a specified sequence and evaluates tracked damage continuity.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import cv2
from ultralytics import YOLO

def run_tracking_benchmark(sequence_dir: Path, weights_path: Path):
    img1_dir = sequence_dir / "img1"
    if not img1_dir.exists():
        print(f"[ERROR] img1 directory not found in {sequence_dir}")
        sys.exit(1)

    frames = sorted(img1_dir.glob("*.jpg"))
    print(f"Tracking sequence: {sequence_dir.name} ({len(frames)} frames)")
    
    model = YOLO(str(weights_path))
    unique_ids = set()
    total_detections = 0

    for idx, f in enumerate(frames, start=1):
        frame = cv2.imread(str(f))
        res = model.track(frame, tracker="bytetrack.yaml", persist=True, verbose=False, conf=0.25)
        if res and res[0].boxes is not None and res[0].boxes.id is not None:
            tids = res[0].boxes.id.int().cpu().tolist()
            unique_ids.update(tids)
            total_detections += len(tids)

    print(f"[RESULTS] Total detections: {total_detections}, Unique persistent damage tracks: {len(unique_ids)}")
    return unique_ids

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sequence", type=Path, required=True, help="Path to sequence directory")
    parser.add_argument("--weights", type=Path, default=Path("weights/cardd-yolov8s-seg.pt"))
    args = parser.parse_args()
    run_tracking_benchmark(args.sequence, args.weights)
