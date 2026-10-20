# Prompt for Antigravity: Build and run Stage 2 edge-case image evaluation

I have provided `stage2_edge_case_dataset_kit`. My goal is to collect a real, legally usable image-only edge-case dataset and test **Stage 2 only** (Dual-Mask Part & Damage Segmentation). Do not run Stage 0 or Stage 1 as part of the evaluation and do not implement Stage 3.

## First inspect the actual repository
Inspect:
- `app/domain/vehicle_identity_continuity/schemas.py`
- `app/domain/dual_mask_segmentation/`
- `tests/dual_mask_segmentation/`
- the Stage 2 LLD and existing fixtures
- model weight files and class mappings
- DB/service requirements of the Stage 2 orchestrator

Confirm the exact fields Stage 2 consumes and whether it reads `scratch_video_path`, requires valid `vehicle_telemetry`, or queries PostgreSQL/Redis. Reuse real test fixtures and isolated test database records. Never invent telemetry, bypass validation, or modify Stage 0/1.

## Acquire actual images
Find real, publicly accessible and legally usable images from research datasets, open-license collections, or dataset publishers. Prioritize:
1. Tiny/low-contrast dents, hairline cracks, faint scratches
2. Crowded parking lots with multiple vehicles and one damaged vehicle
3. Collision scenes/two vehicles touching, overlapping damaged panels
4. Damage near door seams, bumper boundaries, lights, wheel arches
5. Partial occlusion, shadows, glare, low contrast
6. Reflection/shadow/dirt false positives
7. Undamaged negative controls

Aim for 100–200 images if available, but do not pad the dataset. Keep source URL, dataset name, license/terms, attribution, download date, original filename, category and download status in `metadata/source_register.csv`. Do not assume publicly viewable means reusable. Do not fabricate URLs, images, labels or test results. If license is unclear, quarantine the asset from the main evaluation set.

Use real images only in the primary dataset. If synthetic images are later added, store them separately and label them synthetic.

## Prepare annotations
Create `metadata/manifest.csv` and structured annotations under `annotations/`. Record image-level category, damage presence/type, vehicle count, visibility, occlusion, lighting and label verification status. Where feasible, add vehicle-part and damage polygons/masks. Use `unknown` for uncertain ground truth. Never use predictions as ground truth.

## Run Stage 2 only
Build a small evaluation harness that directly invokes the existing Stage 2 orchestrator with a valid `Stage2HandoffPayload` and the dataset JPEGs in `keyframe_paths`. Use the actual schema and existing test fixtures. If Stage 2 needs valid DB rows or telemetry, create isolated test fixtures instead of faking production data. Determine whether the orchestrator requires a scratch video file despite image-only testing; if so, document the minimum legitimate fixture needed.

Run existing Stage 2 tests first, then the direct evaluation. Save per-image predictions, masks/polygons, errors, and an evaluation summary. Report separately:
- in-contract keyframe tests
- adversarial whole-scene multi-car tests that may violate Stage 1's single-vehicle handoff assumptions

Compute metrics only where verified annotations exist. Distinguish model failures from environment/harness failures. Do not change weights or weaken tests just to improve results.

## Safety and scope
Do not modify Stage 0/1 behavior. Do not implement Stage 3. Do not perform destructive database operations. Do not overwrite existing assets. Before making code changes, show the test-harness plan and exact interface.

Start by checking this kit and the repository, then report which data sources are suitable and the exact next steps.
