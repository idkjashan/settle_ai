#!/usr/bin/env python3
"""Organize incoming images into category folders and create a metadata manifest.

This utility does NOT label damage or infer ground truth. Category is inferred only
from a filename prefix and must be manually reviewed.
"""
from pathlib import Path
import csv, hashlib, re
try:
    from PIL import Image
except ImportError:
    raise SystemExit("Install Pillow in your project/kit environment: python -m pip install Pillow")

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming"
IMAGES = ROOT / "images"
MANIFEST = ROOT / "metadata" / "manifest.csv"
CATEGORIES = {
    "subtle_damage", "multi_vehicle", "collision_damage", "part_boundaries",
    "occlusion", "reflections_false_positives", "undamaged_controls"
}
EXTS = {".jpg", ".jpeg", ".png", ".webp"}

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def main():
    rows = []
    for path in sorted(INCOMING.iterdir()):
        if not path.is_file() or path.suffix.lower() not in EXTS:
            continue
        match = re.match(r"([a-z_]+)__", path.stem.lower())
        category = match.group(1) if match else "unknown"
        if category not in CATEGORIES:
            category = "unknown"
        target_dir = IMAGES / category
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / path.name
        if target.exists():
            print(f"SKIP existing target: {target}")
            continue
        # Preserve original bytes/format; don't silently re-encode.
        target.write_bytes(path.read_bytes())
        try:
            with Image.open(target) as im:
                width, height = im.size
                fmt = im.format or target.suffix.lstrip(".").upper()
        except Exception as exc:
            print(f"SKIP unreadable image {target}: {exc}")
            target.unlink(missing_ok=True)
            continue
        aid = "img_" + sha256(target)[:12]
        rows.append([aid, target.relative_to(ROOT).as_posix(), sha256(target),
                     width, height, fmt, category, "unknown", "unknown",
                     "unknown", "unknown", "unknown", "unknown", "unverified",
                     "unassigned", "", "Review category and add source/license metadata."])
        print(f"Added {target.relative_to(ROOT)} [{width}x{height}] category={category}")
    if rows:
        exists = MANIFEST.exists() and MANIFEST.stat().st_size > 0
        with MANIFEST.open("a" if exists else "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["asset_id","relative_path","sha256","width","height","format",
                            "category","damage_present","damage_type","vehicle_count","visibility",
                            "occlusion","lighting","annotation_status","split","source_asset_id","notes"])
            w.writerows(rows)
    print(f"Finished. Added {len(rows)} image(s). No ground-truth labels were generated.")

if __name__ == "__main__":
    main()
