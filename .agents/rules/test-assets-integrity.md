---
id: test-assets-integrity
trigger: "when adding, reorganizing, or modifying test assets or dataset videos"
confidence: 1.0
domain: "test-assets"
scope: project
project_name: "settleai"
---

# Test Asset Integrity & Dataset Purity Protocol

## Action
1. **Never Slice or Edit Existing Videos into Duplicate Clips**: Do not create sub-sequences, sliced trims, or slightly edited clips of existing dataset videos under new or different filenames (e.g. `car_009_flank_orbit.mp4` sliced from `car_009.mp4`, `scenario_01_bumper_crush.mp4` sliced from `scenario_01_damaged_collision.mp4`). Always preserve and use full authentic original videos.
2. **Never Inject Synthetic / Generated Media into Dataset Cohorts**: Do not generate synthetic videos (e.g. `gemini_generated_video_*.mp4`) into dataset folders unless explicitly asked by the user.
3. **Strict Flat Tiering**: Keep `test_assets/videos/simple/` and `test_assets/videos/difficult/` completely flat with zero nested subdirectories.
4. **Clean Manifest Maintenance**: Ensure every file in `simple/` and `difficult/` is strictly cataloged in `test_assets/videos/manifest.json`.

## Evidence
- User explicit reprimand: "reorganise test asset folder see if they have garbage file clear them and delete duplicate video(u have created same video again and again by just editing it a bit and changing name clear them and dont do this again save to memory) or non dataset related video"

