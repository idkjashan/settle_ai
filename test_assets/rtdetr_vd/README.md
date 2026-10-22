# RTDETR-VD & 360° Vehicle Damage Tracking Dataset

Official structured dataset folder for **Vehicle Damage Detection and Multi-Object Tracking** formatted according to the **MOT Challenge** specification.

## Provenance & Sources

1. **RTDETR-VD (Engineering Applications of Artificial Intelligence, 2026)**:
   - Paper: *Vehicle damage detection with transformer-based multi-object tracking*
   - Code & Benchmark Repository: [`jeiva2000/RTDETR-VD`](https://github.com/jeiva2000/RTDETR-VD)
   - Sequences: `aveo`, `VID_20260210_104922`, `VID_20260118_222318`, `rtdetr_demo_portrait`, `rtdetr_demo_landscape`

2. **Cars Dataset - 360° Videos (Kaggle tapakah68)**:
   - Dataset: *Videos around cars - Vehicle dataset*
   - Sequences: `car_001_360_damage`, `car_002_360_damage`, `car_004_360`, `car_006_360`

---

## Directory Structure

```
test_assets/rtdetr_vd/
├── dataset/
│   ├── test/
│   │   ├── aveo/
│   │   │   ├── img1/             # 1-indexed frames (000001.jpg, 000002.jpg...)
│   │   │   ├── gt/gt.txt         # frame,id,x,y,w,h,conf,class,vis
│   │   │   ├── seqinfo.ini       # MOT metadata (resolution, fps, length)
│   │   │   └── aveo.mp4          # H.264 source video
│   │   ├── VID_20260210_104922/
│   │   ├── VID_20260118_222318/
│   │   ├── car_001_360_damage/
│   │   └── car_002_360_damage/
│   ├── val/
│   │   ├── rtdetr_demo_portrait/
│   │   └── rtdetr_demo_landscape/
│   └── train/
│       ├── car_004_360/
│       └── car_006_360/
├── views/                        # Frame-level views with bounding boxes for FP evaluation
│   ├── aveo/
│   ├── car_001/
│   └── ...
├── manifest.json                 # Complete machine-readable sequence catalog
└── tools/
    ├── verify_dataset.py         # Integrity and MOT validation runner
    └── benchmark_tracker.py      # Tracking benchmark runner
```

---

## MOT Ground Truth Format (`gt.txt`)

Conforms strictly to the MOT Challenge format (single-class `damage`):

```csv
<frame>,<track_id>,<bb_left>,<bb_top>,<bb_width>,<bb_height>,<conf>,<class_id>,<visibility>
```

Example row:
`1,1,251,103,90,87,1.0000,-1,1`

---

## Verification & Usage

Run the verification test suite:

```bash
uv run python test_assets/rtdetr_vd/tools/verify_dataset.py
uv run pytest tests/test_rtdetr_vd_dataset.py -v
```
