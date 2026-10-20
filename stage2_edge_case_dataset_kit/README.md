# Auto-Settle AI — Stage 2 Edge-Case Dataset Kit

## What this is
This is a **dataset starter kit** for collecting and evaluating difficult car-damage images against Stage 2 only. It includes a folder structure, manifest template, annotation schema, an asset-organizing helper, and instructions for Antigravity.

**Important:** This kit does not pretend to contain real-world photographs. No source images could be fetched and license-verified in the environment that created this kit. Put lawfully obtained images into `incoming/`, or ask Antigravity to acquire them from public sources and record source/license metadata before adding them.

## Target categories
- `subtle_damage`: low-contrast dents, hairline cracks, fine scratches
- `multi_vehicle`: crowded parking lots, several cars, only one damaged vehicle
- `collision_damage`: two vehicles touching/impact damage, overlapping damaged panels
- `part_boundaries`: damage near door seams, bumper edges, lamps, wheel arches
- `occlusion`: damage partly obscured by another vehicle/object
- `reflections_false_positives`: reflections, shadows, dirt that resemble damage
- `undamaged_controls`: verified undamaged examples for false-positive checks

## Expected Stage 2 input
The intended handoff is `Stage2HandoffPayload`:
- `claim_id: UUID`
- `policy_id: str`
- `scratch_video_path: str`
- `keyframe_paths: Dict[str, str]`
- `vehicle_telemetry: VehicleContinuityTelemetryDTO`

Stage 2's primary vision input is a dictionary of semantic keys to JPEG image paths. **The exact runtime requirements must be verified against the repository's actual Stage 2 code and fixtures.** Some Stage 2 code may require valid telemetry, policy/catalog rows, or a video path even in image-only evaluation. Do not fabricate telemetry or disable checks to force a pass.

## How to use
1. Place source images in `incoming/`. Use filenames that start with a category name, e.g. `subtle_damage__source123.jpg` or `multi_vehicle__parkinglot_01.jpg`.
2. Record source URL and license in `metadata/source_register.csv`.
3. Run `python tools/organize_assets.py` from this directory.
4. Review `metadata/manifest.csv`. The helper does not infer ground truth and deliberately leaves labels unverified.
5. Ask Antigravity to inspect the real Stage 2 implementation, build a valid direct Stage 2 test harness, obtain/annotate assets, and run evaluation.

## Annotation policy
Do not use the model's own predictions as ground truth. Have a human verify damage labels and locations. Use `unknown` when evidence is ambiguous. Only calculate mask metrics for assets with reliable ground-truth masks/polygons.

## Image-only test caveat
Multi-car images are useful adversarial tests, but Stage 2 normally receives keyframes selected by Stage 1 for a specific vehicle. Label whole-scene multi-car tests as `adversarial_out_of_contract` if they violate that assumption. Do not mix those scores with normal in-contract scores.
