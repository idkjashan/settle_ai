# Evaluation Suite & Benchmarking Harness

This directory contains the automated evaluation framework and benchmarking testbench for **Auto-Settle AI**. It validates claims end-to-end across all 7 pipeline stages, running against both authentic video walkarounds and structured photo packs.

---

## 1. Quick Start: Running Evaluations

Execute evaluations using `uv`:

```bash
# Run the 20 canonical evaluation benchmark scenarios
uv run python evals/eval_harness.py

# Launch the interactive Web Testbench GUI (Browser interface on port 8080)
uv run python evals/web_testbench.py

# Execute single video scenario with granular audit trail
uv run python evals/eval_harness.py --video test_assets/videos/simple/car_001.mp4 --claim "Scratched driver door and bumper"

# Run headless Playwright frontend E2E tests
uv run python evals/frontend_e2e_runner.py
```

---

## 2. Benchmark Evaluation Results (20 Canonical Scenarios)

The canonical benchmark in [`evals/eval_report_latest.json`](eval_report_latest.json) evaluates 20 diverse stress-test scenarios (18 video + 2 photo pack) covering real collisions, identity mismatches, adversarial camera tricks, and low-light environments.

**Overall Benchmark Pass Rate: 100.0% (20/20 scenarios passed)**

| Scenario ID | Scenario Name | Modality | Stage 0 Latency | Stage 1 Latency | Stage 2 Status | Billed Parts | Outcome |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `SC-01` | Right Flank Key Scratch | Video | 151.3 ms | 6,373.6 ms | `STAGE_3_VLM_INSPECTION` | `back_right_door`, `front_right_door` | **PASS** |
| `SC-02` | Identity Mismatch (White vs Blue) | Video | 98.6 ms | 3,708.6 ms | Blocked (`ESC-01`) | — | **PASS** |
| `SC-03` | Driver Flank Sideswipe Scratch | Video | 101.0 ms | 1,969.3 ms | `STAGE_3_VLM_INSPECTION` | `front_right_door` | **PASS** |
| `SC-04` | Multi-Panel Flank Sideswipe | Video | 104.9 ms | 1,979.8 ms | `STAGE_3_VLM_INSPECTION` | `back_right_door`, `front_right_door` | **PASS** |
| `SC-05` | Phantom Damage: Rear Lamp & Bumper | Video | 99.5 ms | 1,965.1 ms | Escalated (`ESC-07`) | — | **PASS** |
| `SC-06` | Phantom Damage: Broken Wing Mirror | Video | 96.2 ms | 1,971.9 ms | Escalated (`ESC-07`) | — | **PASS** |
| `SC-07` | Phantom Damage: Hood Hail Dent | Video | 95.0 ms | 1,967.2 ms | Escalated (`ESC-07`) | — | **PASS** |
| `SC-08` | Phantom Damage: Bumper Crush | Video | 96.9 ms | 1,933.9 ms | Escalated (`ESC-07`) | — | **PASS** |
| `SC-09` | Reverse Walkaround Rear Start | Video | 530.4 ms | 17,894.5 ms | `STAGE_3_VLM_INSPECTION` | `back_bumper` | **PASS** |
| `SC-10` | Crowded Parking Lot Occlusion | Video | 600.8 ms | 21,808.9 ms | Escalated (`ESC-07`) | — | **PASS** |
| `SC-11` | Macro Close-Up Zoom (No Plate) | Video | 440.0 ms | 2,489.8 ms | Blocked (`ESC-02`) | — | **PASS** |
| `SC-12` | Overcast to Tree Canopy Shadow | Video | 521.4 ms | 13,335.1 ms | Escalated (`ESC-06`) | — | **PASS** |
| `SC-13` | Pre-existing Damage Quarantine | Video | 102.2 ms | 2,785.1 ms | `STAGE_3_VLM_INSPECTION` | `front_right_door` | **PASS** |
| `SC-14` | Undamaged Negative Control | Video | 612.0 ms | 17,409.4 ms | Escalated (`ESC-07`) | — | **PASS** |
| `SC-15` | Opposite-Side Fraud Attempt | Video | 97.8 ms | 2,038.1 ms | Escalated (`ESC-07`) | — | **PASS** |
| `SC-16` | Faint Scratch vs Reflection Glare | Video | 451.0 ms | 12,471.6 ms | Escalated (`ESC-07`) | — | **PASS** |
| `SC-17` | Low-Light Basement Parking | Video | 82.5 ms | N/A | Blocked (`QUALITY_GATE`) | — | **PASS** |
| `SC-18` | High-Speed Corner Whip-Pan | Video | 539.1 ms | 14,263.9 ms | `STAGE_3_VLM_INSPECTION` | `front_bumper` | **PASS** |
| `SC-19` | Photo Pack: Unproven Door Scratch | Photo | 85.3 ms | 159.4 ms | Escalated (`ESC-07`) | — | **PASS** |
| `SC-20` | Photo Pack: Unproven Lamp & Bumper | Photo | 112.1 ms | 153.2 ms | Escalated (`ESC-07`) | — | **PASS** |

---

## 3. Real Stage Latency Benchmarks

Measured on an NVIDIA GeForce RTX 4060 GPU and modern multi-core CPU:

| Pipeline Stage | Mean Latency | Median Latency | Min Latency | Max Latency | Primary Operation |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Stage 0: Fast-Fail Gate** | **250.9 ms** | 103.6 ms | 82.5 ms | 612.0 ms | Container forensics & visual quality (blur/luminance) |
| **System 1: Intent Grounding** | **6.7 ms** | 6.3 ms | 3.0 ms | 16.0 ms | FastEmbed ONNX token extraction & taxonomy mapping |
| **Stage 1: Identity & Continuity** | **6,667.3 ms** | 2,489.8 ms | 153.2 ms | 21,808.9 ms | Cut detection, plate OCR, CIELAB Color $\Delta E$, tracking |
| **Stage 2: Dual-Mask Segmentation**| **858.8 ms** | 596.1 ms | 425.6 ms | 1,584.6 ms | Dual YOLO Carparts + CarDD, Shapely C-GEOS IoP |

---

## 4. Architecture of the Evaluation Harnesses

- **[`comprehensive_harness.py`](comprehensive_harness.py)**: The master orchestrator. Runs any video/photo pack through Stages 0 to 6 with configurable stage bypassing, automatic keyframe extraction, granular JSON audit logs, and SSE progress event streaming.
- **[`eval_harness.py`](eval_harness.py)**: Automated benchmark runner that reads [`curated_test_manifest.json`](curated_test_manifest.json) and verifies all 20 scenarios against expected escalation codes, pass/fail thresholds, and outputs.
- **[`web_testbench.py`](web_testbench.py)**: Standalone visual testbench running an HTTP server on port 8080. Allows judges to interactively drag-and-drop videos, select test policies, view intermediate YOLO masks, and inspect SoM crops in real-time.
- **[`frontend_e2e_runner.py`](frontend_e2e_runner.py)**: Headless end-to-end testing client that exercises the live claims workstation frontend against the FastAPI backend.
