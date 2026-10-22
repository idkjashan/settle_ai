#!/usr/bin/env python3
"""
Validates the structural integrity and MOT compliance of the RTDETR-VD dataset.
"""
from __future__ import annotations
import configparser
import json
from pathlib import Path
import sys
import cv2

def verify_dataset(dataset_root: Path) -> bool:
    manifest_file = dataset_root / "manifest.json"
    if not manifest_file.exists():
        print(f"[FAIL] Missing manifest.json in {dataset_root}")
        return False
    
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    
    print(f"Loaded manifest: {manifest['dataset_name']} ({len(manifest['sequences'])} sequences)")
    all_ok = True

    for seq_name, meta in manifest["sequences"].items():
        split = meta["split"]
        seq_dir = dataset_root / "dataset" / split / seq_name
        if not seq_dir.is_dir():
            print(f"[FAIL] Missing sequence folder: {seq_dir}")
            all_ok = False
            continue

        # Check seqinfo.ini
        seqinfo_path = seq_dir / "seqinfo.ini"
        if not seqinfo_path.exists():
            print(f"[FAIL] Missing seqinfo.ini in {seq_dir}")
            all_ok = False
            continue
        
        cfg = configparser.ConfigParser()
        cfg.read(seqinfo_path)
        seq_len = int(cfg["Sequence"]["seqLength"])
        w = int(cfg["Sequence"]["imWidth"])
        h = int(cfg["Sequence"]["imHeight"])

        # Check img1 frames
        img1_dir = seq_dir / "img1"
        frames = sorted(img1_dir.glob("*.jpg"))
        if len(frames) != seq_len:
            print(f"[FAIL] Frame count mismatch in {seq_name}: expected {seq_len}, found {len(frames)}")
            all_ok = False
            continue

        # Check sample frame resolution
        sample_img = cv2.imread(str(frames[0]))
        if sample_img is None or sample_img.shape[1] != w or sample_img.shape[0] != h:
            print(f"[FAIL] Image dimension mismatch in {seq_name}: expected ({w}x{h}), found {sample_img.shape[1]}x{sample_img.shape[0]}")
            all_ok = False
            continue

        # Check gt.txt
        gt_path = seq_dir / "gt" / "gt.txt"
        if not gt_path.exists():
            print(f"[FAIL] Missing gt.txt in {seq_dir / 'gt'}")
            all_ok = False
            continue

        # Check MP4
        mp4_path = seq_dir / f"{seq_name}.mp4"
        if not mp4_path.exists():
            print(f"[FAIL] Missing video file: {mp4_path}")
            all_ok = False
            continue

        print(f"[PASS] {split}/{seq_name}: {seq_len} frames ({w}x{h}), {meta['gt_boxes']} GT tracks, video OK")

    return all_ok

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    if not verify_dataset(root):
        sys.exit(1)
    print("\n[SUCCESS] Entire RTDETR-VD dataset verified successfully.")
