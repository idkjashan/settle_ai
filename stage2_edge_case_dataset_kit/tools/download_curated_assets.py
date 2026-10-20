#!/usr/bin/env python3
"""Curated asset collector for Stage 2 edge-case evaluation dataset.

Collects real, legally documented images from:
1. Wikimedia Commons API (Public Domain, CC0, CC-BY, CC-BY-SA)
2. Verified local scenario keyframes (test_assets/keyframes_for_stage2/)

Writes downloaded files into incoming/ with category__ prefix, and records
full licensing, author, and source information into metadata/source_register.csv.
"""
from pathlib import Path
import csv
import hashlib
import json
import re
import shutil
import time
import urllib.parse
import urllib.request

KIT_ROOT = Path(__file__).resolve().parents[1]
INCOMING_DIR = KIT_ROOT / "incoming"
REGISTER_CSV = KIT_ROOT / "metadata" / "source_register.csv"
REPO_ROOT = KIT_ROOT.parent

# Edge-case categories
CATEGORIES = [
    "collision_damage",
    "subtle_damage",
    "multi_vehicle",
    "part_boundaries",
    "occlusion",
    "reflections_false_positives",
    "undamaged_controls",
]

# Wikimedia Commons queries per category
WIKI_QUERIES = {
    "collision_damage": [
        "car crash damaged front bumper",
        "automobile side collision damage impact",
        "car fender bender damaged panel",
        "damaged car traffic accident",
        "crashed car front fender",
    ],
    "subtle_damage": [
        "scratched car paint",
        "car door scratch",
        "automobile door ding paint scrape",
        "car panel minor scratch dent",
        "keyed car door scratch paint",
    ],
    "multi_vehicle": [
        "automobiles parked parking lot rows",
        "cars parked in dealership lot",
        "traffic congestion parked vehicles side by side",
    ],
    "part_boundaries": [
        "damaged car fender bumper",
        "car collision door fender",
        "car damage quarter panel bumper joint",
        "automobile dent front door rear door boundary",
    ],
    "occlusion": [
        "car parked behind tree",
        "vehicle behind fence",
        "car street partially hidden tree shadow",
        "automobile behind street pole barrier",
    ],
    "reflections_false_positives": [
        "glossy car paint reflection",
        "car surface reflection glossy hood paint",
        "car paint puddle reflection glare",
        "automobile glossy reflection tree branches",
    ],
    "undamaged_controls": [
        "automobile exterior front view clean car",
        "car side profile clean dealership showroom",
        "automobile pristine clean exterior panel",
    ],
}

LOCAL_KEYFRAME_MAPPING = [
    # (source_dir, category, youtube_url, car_info)
    ("scenario_01", "collision_damage", "https://www.youtube.com/watch?v=5-D-pNREhb8", "2002 Subaru Impreza WRX (collision damaged)"),
    ("scenario_02", "subtle_damage", "https://www.youtube.com/watch?v=e-UvvPFLDnU", "2018 Ford Mustang GT (macro scratch / seam)"),
    ("scenario_03", "multi_vehicle", "https://www.youtube.com/watch?v=h8ld2x3hs8Y", "2022 Lexus NX 350h (parking lot multi-car)"),
    ("scenario_04", "undamaged_controls", "https://www.youtube.com/watch?v=ddZFNxRHgGY", "2007 Honda Accord (reverse walkaround)"),
    ("scenario_05", "reflections_false_positives", "https://www.youtube.com/watch?v=x8NmCLv9Yq8", "2011 Mercedes-Benz E350 (overcast canopy shadows)"),
    ("real_toyota_hilux_white_ute", "undamaged_controls", "https://www.youtube.com/watch?v=ohg7L1sG9k4", "2021 Toyota Hilux SR5 (clean white exterior)"),
    ("real_fiat_500_blue_hatchback", "undamaged_controls", "https://www.youtube.com/watch?v=k0HQOb9h4vw", "2023 Fiat 500 Dolcevita (clean blue exterior)"),
    ("real_vw_golf_grey_hatchback", "undamaged_controls", "https://www.youtube.com/watch?v=4JtTvlaF3jw", "2024 Volkswagen Golf (clean dark grey exterior)"),
    ("real_ferrari_360_silver_coupe", "reflections_false_positives", "https://www.youtube.com/watch?v=J86z4xMMcfE", "1999 Ferrari 360 Modena (glossy silver reflection)"),
]


def strip_html(text: str) -> str:
    """Remove HTML tags from artist / credit strings."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    return clean.strip()


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_wikimedia_images(target_per_category: int = 12):
    """Query Wikimedia Commons API and download verified images."""
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    downloaded_records = []

    user_agent = "SettleAIEdgeCaseDatasetCollector/1.0 (https://github.com/settle_ai; contact@settleai.org)"

    for category, queries in WIKI_QUERIES.items():
        print(f"\n[Wikimedia Commons] Fetching category: {category}...")
        count = 0
        for q in queries:
            if count >= target_per_category:
                break
            encoded_q = urllib.parse.quote(q)
            api_url = (
                f"https://commons.wikimedia.org/w/api.php?action=query"
                f"&generator=search&gsrsearch={encoded_q}&gsrnamespace=6"
                f"&gsrlimit=10&prop=imageinfo&iiprop=url|size|extmetadata&format=json"
            )
            req = urllib.request.Request(api_url, headers={"User-Agent": user_agent})
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                print(f"  Warning: search query '{q}' failed: {e}")
                continue

            pages = data.get("query", {}).get("pages", {})
            for pid, page in pages.items():
                if count >= target_per_category:
                    break
                imageinfo_list = page.get("imageinfo", [])
                if not imageinfo_list:
                    continue
                info = imageinfo_list[0]
                img_url = info.get("url")
                if not img_url:
                    continue

                # Check extension (JPEG or PNG only)
                ext = Path(urllib.parse.urlparse(img_url).path).suffix.lower()
                if ext not in [".jpg", ".jpeg", ".png"]:
                    continue

                width = info.get("width", 0)
                height = info.get("height", 0)
                if width < 400 or height < 300:
                    continue

                meta = info.get("extmetadata", {})
                license_short = meta.get("LicenseShortName", {}).get("value", "Unknown")
                license_url = meta.get("LicenseUrl", {}).get("value", "")
                artist = strip_html(meta.get("Artist", {}).get("value", "Unknown"))
                usage_terms = meta.get("UsageTerms", {}).get("value", "")

                # Legal compliance check: CC, PD, or Public Domain
                is_pd = any(term in license_short.lower() for term in ["public domain", "cc0", "pd"])
                is_cc = "cc" in license_short.lower()
                if not (is_pd or is_cc):
                    # Quarantine assets without clear open license
                    continue

                is_commercial_ok = not ("nc" in license_short.lower())
                attribution_required = not is_pd

                # Generate clean filename
                safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", page.get("title", f"wiki_{pid}"))[:40]
                incoming_filename = f"{category}__wiki_{pid}_{safe_title}{ext}"
                target_path = INCOMING_DIR / incoming_filename

                if target_path.exists():
                    print(f"  Skip existing: {incoming_filename}")
                    continue

                print(f"  Downloading: {target_path.name} (License: {license_short})")
                try:
                    img_req = urllib.request.Request(img_url, headers={"User-Agent": user_agent})
                    with urllib.request.urlopen(img_req, timeout=25) as img_resp:
                        img_bytes = img_resp.read()
                    target_path.write_bytes(img_bytes)
                except Exception as e:
                    print(f"    Failed download for {img_url}: {e}")
                    if target_path.exists():
                        target_path.unlink()
                    continue

                f_sha256 = sha256_of_file(target_path)
                aid = f"img_{f_sha256[:12]}"

                record = {
                    "asset_id": aid,
                    "filename": incoming_filename,
                    "category": category,
                    "source_dataset_or_site": "Wikimedia Commons",
                    "source_url": img_url,
                    "license_name": license_short,
                    "license_url_or_terms": license_url or usage_terms,
                    "attribution_required": "yes" if attribution_required else "no",
                    "commercial_use_confirmed": "yes" if is_commercial_ok else "no",
                    "download_date": time.strftime("%Y-%m-%d"),
                    "download_status": "verified_download",
                    "notes": f"Author/Artist: {artist}. Usage terms: {usage_terms}",
                }
                downloaded_records.append(record)
                count += 1
                time.sleep(0.3)  # Be polite to Wikimedia API

    return downloaded_records


def copy_local_scenario_keyframes(max_per_scenario: int = 5):
    """Safely copy select keyframes from test_assets/keyframes_for_stage2/ without modifying originals."""
    local_records = []
    keyframes_root = REPO_ROOT / "test_assets" / "keyframes_for_stage2"
    if not keyframes_root.exists():
        print("Local keyframes directory not found. Skipping local copy.")
        return local_records

    print("\n[Local Keyframes] Copying verified scenario keyframes...")
    for subfolder, category, yt_url, car_info in LOCAL_KEYFRAME_MAPPING:
        source_dir = keyframes_root / subfolder
        if not source_dir.exists():
            continue

        # Find keyframes (prioritize canonical ones or keyframe_*.jpg)
        candidates = sorted(source_dir.glob("*.jpg"))
        selected = candidates[:max_per_scenario]

        for src_file in selected:
            dest_name = f"{category}__local_{subfolder}_{src_file.name}"
            dest_path = INCOMING_DIR / dest_name
            if dest_path.exists():
                continue

            shutil.copy2(src_file, dest_path)
            f_sha256 = sha256_of_file(dest_path)
            aid = f"img_{f_sha256[:12]}"

            record = {
                "asset_id": aid,
                "filename": dest_name,
                "category": category,
                "source_dataset_or_site": "internal_test_suite_walkaround_video",
                "source_url": yt_url,
                "license_name": "YouTube Standard License / Research & Internal Benchmarking Only",
                "license_url_or_terms": "https://www.youtube.com/t/terms",
                "attribution_required": "yes",
                "commercial_use_confirmed": "no",
                "download_date": time.strftime("%Y-%m-%d"),
                "download_status": "extracted_local_keyframe",
                "notes": f"Copied from {src_file.relative_to(REPO_ROOT)}. Vehicle: {car_info}. Non-commercial research evaluation.",
            }
            local_records.append(record)
            print(f"  Copied: {dest_name} (from {src_file.name})")

    return local_records


def append_to_source_register(records):
    """Append newly collected records to metadata/source_register.csv."""
    if not records:
        print("No new records to write to source register.")
        return

    fieldnames = [
        "asset_id",
        "filename",
        "category",
        "source_dataset_or_site",
        "source_url",
        "license_name",
        "license_url_or_terms",
        "attribution_required",
        "commercial_use_confirmed",
        "download_date",
        "download_status",
        "notes",
    ]

    existing_filenames = set()
    file_exists = REGISTER_CSV.exists() and REGISTER_CSV.stat().st_size > 0
    if file_exists:
        with REGISTER_CSV.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_filenames.add(row.get("filename"))

    to_write = [r for r in records if r["filename"] not in existing_filenames]
    if not to_write:
        print("All records already present in source register.")
        return

    with REGISTER_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(to_write)

    print(f"\nWrote {len(to_write)} records to {REGISTER_CSV.relative_to(KIT_ROOT)}.")


def main():
    print("=== Auto-Settle AI: Stage 2 Edge-Case Asset Collector ===")
    wiki_records = fetch_wikimedia_images(target_per_category=12)
    local_records = copy_local_scenario_keyframes(max_per_scenario=5)

    all_records = wiki_records + local_records
    append_to_source_register(all_records)
    print(f"\nAsset collection complete: Total {len(all_records)} assets in incoming directory.")


if __name__ == "__main__":
    main()
