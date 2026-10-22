# Video Test Assets Catalog

This directory houses the curated video cohort for **Auto-Settle AI** pipeline validation, organized into two flat tiers: `simple/` and `difficult/`.

## Directory Structure

```
test_assets/videos/
├── manifest.json       # Machine-readable metadata, resolution, FPS, duration, and rationale
├── README.md           # Documentation of tiers and classification rationale
├── simple/             # Functional baseline videos (25 authentic walkarounds & dataset sequences)
│   ├── 1.mp4 ... 10.mp4                                      # Authentic walkaround video sequences
│   ├── VID_20260118_222318.mp4
│   ├── VID_20260210_104922.mp4
│   ├── aveo.mp4
│   ├── car_001.mp4 ... car_011.mp4
│   ├── rtdetr_demo_landscape.mp4
│   ├── rtdetr_demo_portrait.mp4
│   └── toyota-corolla-side-impact-damage-walkaround-houston.mp4  # Houston side-impact collision walkaround
└── difficult/          # Edge cases, adversarial scenarios, and stress conditions (10 authentic videos)
    ├── ferrari_360_silver_coupe.mp4
    ├── fiat_500_blue_hatchback.mp4
    ├── intel_car_detection.mp4
    ├── scenario_01_damaged_collision.mp4
    ├── scenario_02_macro_closeup_scratch.mp4
    ├── scenario_03_parking_lot_multicar.mp4
    ├── scenario_04_reverse_walkaround_rear_start.mp4
    ├── scenario_05_challenging_lighting_overcast_canopy.mp4
    ├── toyota_hilux_white_ute.mp4
    └── vw_golf_grey_hatchback.mp4
```

> [!NOTE]
> All subdirectories within `simple/` and `difficult/` are strictly disallowed. Only unique, authentic dataset media is stored. Duplicate video slicing and synthetic assets are strictly prohibited.

---

## 1. Simple Tier (`simple/`) — 14 Videos

**Objective**: Verify baseline pipeline functionality, detection accuracy, segmentation boundaries, and multi-turn negotiation without triggering adversarial fast-fails.

- **Characteristics**:
  - Unoccluded vehicle in frame with clear contrast.
  - Smooth 360° perimeter camera orbits or steady inspection pans.
  - Consistent daylight illumination without severe specular glare or shadow flicker.
  - Visible vehicle license plate anchor early in the video.

| Filename | Vehicle | Resolution | FPS | Duration | Key Feature |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `VID_20260118_222318.mp4` | Sedan | 360x668 | 10.0 | 4.0s | Multi-view damage continuity |
| `VID_20260210_104922.mp4` | Compact SUV | 400x224 | 10.0 | 6.0s | Steady outdoor daylight inspection |
| `aveo.mp4` | Chevrolet Aveo | 400x226 | 10.0 | 6.0s | RTDETR-VD benchmark test sequence |
| `car_001.mp4` | Silver Hatchback | 360x640 | 25.0 | 20.6s | Full 360° orbit (dents, cracks, scratches) |
| `car_002.mp4` | Black Luxury Sedan | 1280x720 | 30.0 | 18.0s | 720p HD orbit (paint finish & scrapes) |
| `car_004.mp4` | White Crossover | 360x640 | 30.0 | 12.0s | Clean vs scrape panel contrast |
| `car_005.mp4` | Grey Hatchback | 360x640 | 30.0 | 8.0s | Compact diffuse daylight orbit |
| `car_006.mp4` | Red Sedan | 360x640 | 30.0 | 11.8s | Metallic red finish tracking |
| `car_007.mp4` | SUV / Wagon | 1280x720 | 29.97 | 30.1s | 30s slow steady 360° orbit |
| `car_008.mp4` | Silver Sedan | 360x640 | 30.0 | 8.0s | Quick smooth perimeter sweep |
| `car_009.mp4` | White Sedan | 1280x720 | 59.94 | 65.0s | 60 FPS ultra-smooth long orbit |
| `car_011.mp4` | Blue Hatchback | 360x640 | 30.0 | 5.0s | 5s rapid inspection sweep |
| `rtdetr_demo_landscape.mp4` | Inspection Sedan | 640x362 | 12.0 | 15.4s | Multi-part inspection walkaround |
| `rtdetr_demo_portrait.mp4` | Inspection Hatchback | 420x746 | 12.0 | 14.7s | Vertical smartphone claimant framing |

---

## 2. Difficult Tier (`difficult/`) — 10 Videos

**Objective**: Stress-test anti-fraud gates, trajectory continuity, lighting robustness, multi-vehicle discrimination, and surveyor escalation triggers.

- **Characteristics**:
  - Severe physical impact damage causing boundary deformation.
  - Adversarial macro zoom inspections missing license plate anchors.
  - Multi-vehicle dealership lot occlusions.
  - Dynamic specular glare, overcast shadows, or tree canopy flicker.

| Filename | Vehicle | Resolution | FPS | Duration | Challenge Tested |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `ferrari_360_silver_coupe.mp4` | Ferrari 360 Modena (2001) | 1920x1080 | 30.0 | 20.0s | Low ground clearance with deep road shadows |
| `fiat_500_blue_hatchback.mp4` | Fiat 500 Dolcevita (2023) | 1908x1080 | 30.0 | 21.0s | Curved metallic teal panels with reflections |
| `intel_car_detection.mp4` | Traffic Scene | 768x432 | 12.5 | 30.2s | Heavy traffic scene with multiple moving distractors |
| `scenario_01_damaged_collision.mp4` | 2002 Subaru Impreza WRX | 1920x1080 | 30.0 | 18.0s | Crumpled bumper, buckled hood, deformed fender |
| `scenario_02_macro_closeup_scratch.mp4` | 2018 Ford Mustang GT | 1920x1080 | 30.0 | 20.0s | Macro zoom without plate anchor (`ESC-02`) |
| `scenario_03_parking_lot_multicar.mp4` | 2022 Lexus NX 350h | 1920x1080 | 50.0 | 20.0s | Multi-car dealership lot with distractor vehicles |
| `scenario_04_reverse_walkaround_rear_start.mp4` | 2007 Honda Accord | 1920x1080 | 30.0 | 20.0s | Reverse trajectory starting from rear bumper |
| `scenario_05_challenging_lighting_overcast_canopy.mp4` | 2011 Mercedes-Benz E350 | 1920x1080 | 29.97 | 21.0s | Dynamic tree canopy shadows mimicking scratch lines |
| `toyota_hilux_white_ute.mp4` | Toyota Hilux SR5 (2021) | 1920x1080 | 59.94 | 15.0s | Direct sunlight with specular white paint glare |
| `vw_golf_grey_hatchback.mp4` | Volkswagen Golf (2024) | 1920x1080 | 30.0 | 21.0s | Diffused overcast low-contrast dark grey finish |
