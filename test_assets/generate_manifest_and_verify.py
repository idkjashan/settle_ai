import json
import subprocess
import os

FFPROBE = "/home/jashan/.local/bin/ffprobe"
VIDEOS_DIR = "/home/jashan/settleai/test_assets/scenario_videos"
MANIFEST_PATH = os.path.join(VIDEOS_DIR, "manifest.json")

scenarios_meta = {
    "scenario_01_damaged_collision.mp4": {
        "scenario_id": "scenario_01",
        "scenario_type": "damaged_dented_collision",
        "car_make_model": "2002 Subaru Impreza WRX",
        "car_color": "Blue",
        "damage_description": "Severe collision damage: crumpled front bumper, buckled hood, deformed front fender, and smashed rear quarter panel/window.",
        "source_url": "https://www.youtube.com/watch?v=5-D-pNREhb8"
    },
    "scenario_02_macro_closeup_scratch.mp4": {
        "scenario_id": "scenario_02",
        "scenario_type": "macro_closeup_inspection",
        "car_make_model": "2018 Ford Mustang GT 5.0 Convertible",
        "car_color": "Magnetic Grey",
        "damage_description": "Close-up macro inspection zoom focusing along the rear quarter panel and bumper seam scratch line with inspector gesture.",
        "source_url": "https://www.youtube.com/watch?v=e-UvvPFLDnU"
    },
    "scenario_03_parking_lot_multicar.mp4": {
        "scenario_id": "scenario_03",
        "scenario_type": "parking_lot_multicar_occlusion",
        "car_make_model": "2022 Lexus NX 350h",
        "car_color": "Black",
        "damage_description": "Multi-car dealership lot walkaround testing tracker discrimination against adjacent vehicles (Toyota C-HR, Honda CR-V).",
        "source_url": "https://www.youtube.com/watch?v=h8ld2x3hs8Y"
    },
    "scenario_04_reverse_walkaround_rear_start.mp4": {
        "scenario_id": "scenario_04",
        "scenario_type": "reverse_walkaround_rear_start",
        "car_make_model": "2007 Honda Accord",
        "car_color": "Dark Blue",
        "damage_description": "Reverse trajectory walkaround starting at the rear bumper and plate (CJ09025), sweeping the driver flank to reveal the front fascia.",
        "source_url": "https://www.youtube.com/watch?v=ddZFNxRHgGY"
    },
    "scenario_05_challenging_lighting_overcast_canopy.mp4": {
        "scenario_id": "scenario_05",
        "scenario_type": "challenging_lighting_overcast_canopy",
        "car_make_model": "2011 Mercedes-Benz E350 4MATIC Wagon",
        "car_color": "Iridium Silver Metallic",
        "damage_description": "Complex outdoor lighting walkaround featuring diffused overcast illumination and dynamic tree canopy shadow patterns.",
        "source_url": "https://www.youtube.com/watch?v=x8NmCLv9Yq8"
    }
}

def probe_video(filepath):
    cmd = [
        FFPROBE,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        filepath
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)
    
    # Video stream
    vstream = next(s for s in data["streams"] if s["codec_type"] == "video")
    
    width = int(vstream["width"])
    height = int(vstream["height"])
    codec = vstream["codec_name"]
    pix_fmt = vstream["pix_fmt"]
    
    # Calculate FPS
    r_frame_rate = vstream.get("r_frame_rate", "30/1")
    num, den = map(int, r_frame_rate.split("/"))
    fps = round(num / den, 2)
    
    # Duration
    duration = float(data["format"].get("duration", vstream.get("duration", 0)))
    
    # Check audio streams
    has_audio = any(s["codec_type"] == "audio" for s in data["streams"])
    
    return {
        "codec": codec,
        "pix_fmt": pix_fmt,
        "width": width,
        "height": height,
        "fps": fps,
        "duration_sec": round(duration, 2),
        "has_audio": has_audio,
        "size_bytes": int(data["format"]["size"])
    }

def main():
    manifest_entries = []
    print("Verifying scenario videos...")
    
    all_passed = True
    for filename, meta in scenarios_meta.items():
        filepath = os.path.join(VIDEOS_DIR, filename)
        if not os.path.exists(filepath):
            print(f"ERROR: {filename} missing!")
            all_passed = False
            continue
        
        probe = probe_video(filepath)
        print(f"\n--- {filename} ---")
        print(f"Codec: {probe['codec']} (expected h264)")
        print(f"Pix Fmt: {probe['pix_fmt']} (expected yuv420p)")
        print(f"Audio: {probe['has_audio']} (expected False)")
        print(f"Resolution: {probe['width']}x{probe['height']} (min 720p)")
        print(f"FPS: {probe['fps']} (min 15)")
        print(f"Duration: {probe['duration_sec']}s (expected 10s - 25s)")
        print(f"Size: {probe['size_bytes'] / (1024*1024):.2f} MB")
        
        # Validations
        assert probe["codec"] == "h264", f"Invalid codec: {probe['codec']}"
        assert probe["pix_fmt"] == "yuv420p", f"Invalid pix_fmt: {probe['pix_fmt']}"
        assert not probe["has_audio"], "Audio stream should be stripped"
        assert probe["width"] >= 1280 or probe["height"] >= 720, "Resolution below 720p"
        assert probe["fps"] >= 15.0, "FPS below 15"
        assert 10.0 <= probe["duration_sec"] <= 25.0, f"Duration out of range: {probe['duration_sec']}"
        
        entry = {
            "scenario_id": meta["scenario_id"],
            "scenario_type": meta["scenario_type"],
            "filename": filename,
            "filepath": filepath,
            "car_make_model": meta["car_make_model"],
            "car_color": meta["car_color"],
            "damage_description": meta["damage_description"],
            "duration_sec": probe["duration_sec"],
            "resolution": f"{probe['width']}x{probe['height']}",
            "fps": probe["fps"],
            "source_url": meta["source_url"]
        }
        manifest_entries.append(entry)

    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest_entries, f, indent=2)
    print(f"\nSuccessfully wrote manifest with {len(manifest_entries)} entries to {MANIFEST_PATH}")

if __name__ == "__main__":
    main()
