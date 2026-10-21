# Auto-Settle AI: End-to-End Evaluation Harness & Artifacts Guide

## 1. Overview & Architecture

The Auto-Settle AI evaluation harness ([`evals/e2e_scenario_eval_harness.py`](file:///home/jashan/settleai/evals/e2e_scenario_eval_harness.py)) executes complete claims through all active stages:
1. **Stage 0 Fast-Fail Gate**: Container format, resolution, frame rate, duration, luminance, and Laplacian sharpness.
2. **System 1 Intent Grounder**: Local ONNX embedding-based extraction of claimed parts, damage types, and directional qualifiers.
3. **Stage 1 Vehicle Identity & Continuity**: Cut detector, license plate OCR, HSV color grounding, and ByteTrack keyframe extraction.
4. **Stage 2 Dual-Mask Segmentation**: Carparts-Seg + CarDD-Seg inference at 1024px, Shapely 2.0 polygon intersection over part (IoP), intent conditioning, OEM parts catalogue lookup, and Set-of-Marks (SoM) visual artifact generation.

---

## 2. Running the Evaluation Harness

```bash
# Run full 20-scenario benchmark suite
uv run python evals/e2e_scenario_eval_harness.py --manifest evals/curated_test_manifest.json

# Run a specific scenario by ID (e.g., SC-01)
uv run python evals/e2e_scenario_eval_harness.py --manifest evals/curated_test_manifest.json --scenario SC-01
```

---

## 3. Output Locations & Artifacts

### A. Evaluation Run Reports
Every execution writes a structured JSON report containing stage-by-stage timings, extracted telemetry, detected plates, measured color HSV distances, detected damage masks, and pass/fail verdicts:
- **Latest Run Report**: [`evals/eval_report_latest.json`](file:///home/jashan/settleai/evals/eval_report_latest.json)
- **Timestamped Archive**: `evals/eval_report_YYYYMMDD_HHMMSS.json`

### B. Extracted Video Keyframes
Keyframes extracted along the walkaround trajectory are persisted atomically:
- **Directory**: `/tmp/autosettle_keyframes/<claim_id>/`
- **Files**:
  - `front_bumper.jpg` (canonical front plate anchor)
  - `side_body_panel.jpg` (canonical side overview)
  - `damage_closeup_primary.jpg` (canonical damage inspection zoom)
  - `keyframe_01.jpg` .. `keyframe_21.jpg` (trajectory path samples)

### C. Polygon-Annotated Damage & Set-of-Marks (SoM) Images
For each admitted damage candidate, Stage 2 renders raw bounding crops, dilated polygon contour overlays, and normalized SVG vector masks:
- **Persistent Repository Directory**: [`evals/artifacts/som_output/<claim_id>/`](file:///home/jashan/settleai/evals/artifacts/som_output/)
- **Runtime Temp Directory**: `/tmp/autosettle_som/<claim_id>/`
- **Artifact Files**:
  - `<part_key>_raw.jpg`: Padded crop of the damaged panel without markings.
  - `<part_key>_som.jpg`: Padded crop with cyan/yellow dilated exterior polygon contours (`(255, 255, 0)`) and panel label tag `[#N PART_KEY | DAMAGE_CLASS]`.
  - `<part_key>_mask.svg`: Normalized SVG vector boundary polygon for VLM grounding.

#### Sample Annotated Output Locations from Latest 20/20 Run:
| Scenario ID | Claim ID | Grounded Part | Annotated Polygon Image | Raw Crop |
| :--- | :--- | :--- | :--- | :--- |
| **SC-01** | `ad60d3d2-d6f0-4ccc-bec9-79f54ab89f49` | `front_right_door` | [`evals/artifacts/som_output/ad60d3d2-d6f0-4ccc-bec9-79f54ab89f49/front_right_door_som.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/ad60d3d2-d6f0-4ccc-bec9-79f54ab89f49/front_right_door_som.jpg) | [`front_right_door_raw.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/ad60d3d2-d6f0-4ccc-bec9-79f54ab89f49/front_right_door_raw.jpg) |
| **SC-01** | `ad60d3d2-d6f0-4ccc-bec9-79f54ab89f49` | `back_right_door` | [`evals/artifacts/som_output/ad60d3d2-d6f0-4ccc-bec9-79f54ab89f49/back_right_door_som.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/ad60d3d2-d6f0-4ccc-bec9-79f54ab89f49/back_right_door_som.jpg) | [`back_right_door_raw.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/ad60d3d2-d6f0-4ccc-bec9-79f54ab89f49/back_right_door_raw.jpg) |
| **SC-03** | `2ffe5d58-0644-4647-ad0a-124b8082a7f7` | `front_right_door` | [`evals/artifacts/som_output/2ffe5d58-0644-4647-ad0a-124b8082a7f7/front_right_door_som.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/2ffe5d58-0644-4647-ad0a-124b8082a7f7/front_right_door_som.jpg) | [`front_right_door_raw.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/2ffe5d58-0644-4647-ad0a-124b8082a7f7/front_right_door_raw.jpg) |
| **SC-04** | `446b9fed-08b8-43da-9c24-027e84996b47` | `front_right_door` | [`evals/artifacts/som_output/446b9fed-08b8-43da-9c24-027e84996b47/front_right_door_som.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/446b9fed-08b8-43da-9c24-027e84996b47/front_right_door_som.jpg) | [`front_right_door_raw.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/446b9fed-08b8-43da-9c24-027e84996b47/front_right_door_raw.jpg) |
| **SC-04** | `446b9fed-08b8-43da-9c24-027e84996b47` | `back_right_door` | [`evals/artifacts/som_output/446b9fed-08b8-43da-9c24-027e84996b47/back_right_door_som.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/446b9fed-08b8-43da-9c24-027e84996b47/back_right_door_som.jpg) | [`back_right_door_raw.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/446b9fed-08b8-43da-9c24-027e84996b47/back_right_door_raw.jpg) |
| **SC-09** | `47a433f3-1342-4c2d-bab3-c96701273fdf` | `back_bumper` | [`evals/artifacts/som_output/47a433f3-1342-4c2d-bab3-c96701273fdf/back_bumper_som.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/47a433f3-1342-4c2d-bab3-c96701273fdf/back_bumper_som.jpg) | [`back_bumper_raw.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/47a433f3-1342-4c2d-bab3-c96701273fdf/back_bumper_raw.jpg) |
| **SC-13** | `5a17bfc6-9742-4480-85b3-c922aa9e126c` | `front_right_door` | [`evals/artifacts/som_output/5a17bfc6-9742-4480-85b3-c922aa9e126c/front_right_door_som.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/5a17bfc6-9742-4480-85b3-c922aa9e126c/front_right_door_som.jpg) | [`front_right_door_raw.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/5a17bfc6-9742-4480-85b3-c922aa9e126c/front_right_door_raw.jpg) |
| **SC-18** | `d09cd7ac-1cf2-471e-ad53-16c5f423ed3c` | `front_bumper` | [`evals/artifacts/som_output/d09cd7ac-1cf2-471e-ad53-16c5f423ed3c/front_bumper_som.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/d09cd7ac-1cf2-471e-ad53-16c5f423ed3c/front_bumper_som.jpg) | [`front_bumper_raw.jpg`](file:///home/jashan/settleai/evals/artifacts/som_output/d09cd7ac-1cf2-471e-ad53-16c5f423ed3c/front_bumper_raw.jpg) |

---

## 4. Scenario Catalog Breakdown (20 Cases)

| Cluster | Scenario IDs | Description | Intended Outcome |
| :--- | :--- | :--- | :--- |
| **1. Genuine Physical Claims** | `SC-01`, `SC-03`, `SC-04`, `SC-09`, `SC-18` | Key scratches, sideswipes, and reverse walkarounds with matching vehicle damage. | `STAGE_3_VLM_INSPECTION` (Parts billed) |
| **2. Vehicle Identity Fraud** | `SC-02` | Submitting video of a White vehicle against a Blue Subaru policy (`POL-WRX-014`). | Stage 1 `ESC-01` (Identity Mismatch) |
| **3. Phantom Damage Deterrence** | `SC-05`, `SC-06`, `SC-07`, `SC-08` | Claiming unverified panels (broken mirror, hail hood dent) on intact components. | Stage 2 `ESC-07` (Claimed Damage Not Found) |
| **4. Environmental Edge Cases** | `SC-10`, `SC-12`, `SC-16` | Parking lot occlusions, dynamic tree canopy shadows, paint reflections/swirls. | `ESC-06` (Safety Critical) / `ESC-07` (Manual Adjuster) |
| **5. Severe Capture Failures** | `SC-11`, `SC-17` | Close-up macro without initial plate anchor, pitch-black basement parking. | `ESC-02` (Macro Missing Anchor), `REJECTED_STAGE0` |
| **6. Photo Pack Integrity** | `SC-19`, `SC-20` | Photo pack submissions lacking clear panel damage closeups. | `ESC-07` (Escalate to Adjuster) |

