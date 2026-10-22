<div align="center">

# 🚗 Auto-Settle AI
### Autonomous Video-to-Cash Motor Claims Adjuster

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![PyTorch 2.6](https://img.shields.io/badge/PyTorch-2.6%20CUDA-EE4C2C.svg)](https://pytorch.org/)
[![Ultralytics YOLO](https://img.shields.io/badge/Ultralytics-YOLO11%20%7C%20YOLOv8-00FFFF.svg)](https://docs.ultralytics.com/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16%20Async-336791.svg)](https://www.postgresql.org/)
[![Redis 7](https://img.shields.io/badge/Redis-7%20PubSub-DC382D.svg)](https://redis.io/)
[![Tests Passing](https://img.shields.io/badge/Tests-494%2F494%20Passing-brightgreen.svg)](https://github.com/idkjashan/settle_ai)
[![Benchmark](https://img.shields.io/badge/Benchmark-20%2F20%20Passed%20(100%25)-success.svg)](evals/README.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*An autonomous, fraud-resilient motor claims platform that converts an unbroken 15-second smartphone walkaround video or structured 3–6 photo pack with natural language intent grounding into a cryptographically signed cash settlement voucher in under 90 seconds—reducing physical surveyor overhead from ₹3,500 to under ₹5.*

[**Live Claims Desk**](http://127.0.0.1:8000/) • [**Interactive Web Testbench**](evals/README.md) • [**Evaluation Benchmarks**](#-rigorous-benchmark-evaluations-100-pass-rate) • [**Architecture Docs**](docs/README.md)

</div>

---

## 📌 Contents
1. [Executive Summary & Problem Statement](#-executive-summary--problem-statement)
2. [Why "Naive AI" Fails vs. Auto-Settle AI](#-why-naive-ai-fails-vs-auto-settle-ai)
3. [End-to-End System Architecture](#-end-to-end-system-architecture)
4. [Key Engineering Innovations](#-key-engineering-innovations)
5. [Pipeline Stages Deep-Dive](#-pipeline-stages-deep-dive)
6. [Rigorous Benchmark Evaluations (100% Pass Rate)](#-rigorous-benchmark-evaluations-100-pass-rate)
7. [Repository Structure](#-repository-structure)
8. [Quickstart & Demo Walkthrough](#-quickstart--demo-walkthrough)
9. [Automated Test Suite (494 Tests)](#-automated-test-suite-494-tests)

---

## 🎯 Executive Summary & Problem Statement

In motor insurance worldwide, **over 80% of claims represent minor exterior damage**: bumper scuffs, parking dents, minor fender scrapes, or broken wing mirrors (typically under ₹25,000 / $300).

Despite their simplicity, traditional settlement is fundamentally broken:
- **5 to 7 Days Resolution Time**: Claimants endure manual scheduling, physical surveyor visits, and garage downtime.
- **High Surveyor Overhead**: Insurers spend ₹3,000 to ₹5,000 per claim just to dispatch a human assessor for a ₹6,000 scratch.
- **Subjective Estimating & Leakage**: Human surveyors rely on variable garage estimates with inconsistent labor markups.

**Auto-Settle AI** automates this entire lifecycle with an algorithmic, cost-cascaded pipeline:
1. **Perimeter Forensics & Grounding**: Analyzes an unbroken 15-second walkaround video or structured 3–6 photo pack, cross-referencing vehicle registration (ANPR) and paint color (CIELAB) against policy ground truth.
2. **Intent-Conditioned Quarantine**: Uses real-time local NLP embeddings to extract claimed damage items, quarantining pre-existing road wear so claimants are compensated fairly without false fraud accusations.
3. **Scale-Invariant Geometry**: Normalizes damage using Intersection over Part ($\text{IoP}$) to eliminate camera distance zoom distortion.
4. **Deterministic Actuarial Math**: Calculates repair economics with zero LLM hallucination using official OEM parts catalogs, IRDAI depreciation schedules, and No-Claim Bonus (NCB) protection advice.
5. **Instant Instant Cash Disbursement**: An interactive, mathematically bounded negotiation chatbot settles claims on the spot with cryptographic HMAC-SHA256 signatures and instant UPI voucher generation.

- **End-to-End Latency**: $< 90\text{ seconds}$ from upload to instant cash payout.
- **Operating Compute Cost**: Slashed from ₹3,500 physical surveyor cost to $< ₹5$ per claim.

---

## ⚠️ Why "Naive AI" Fails vs. Auto-Settle AI

Many prototypes attempt claims processing by sending raw photos directly to general-purpose Vision-Language Models (VLMs) like GPT-4o. In production, this approach fails catastrophically:

| Failure Mode | Naive VLM Prompting Vulnerability | Auto-Settle AI Production Defense |
| :--- | :--- | :--- |
| **Static Photo Spoofing** | Fraudsters upload Google Images or photograph someone else's damaged vehicle in a parking lot. | **Continuous Trajectory & ANPR Grounding**: Enforces continuous ByteTrack tracking across 360° video orbits, or mandatory plate-anchored photo packs verified against ANPR OCR and CIELAB paint distance. |
| **Unconditioned Blind Detection** | Computer vision detects every scratch on the car (including 5-year-old road wear), generating inflated payouts or false fraud alarms (`ESC-05`). | **Conditioned Damage Quarantine Engine**: Fast local embeddings (`FastEmbed ONNX`) parse claimant intent. Admitted damage is billed; unclaimed peripheral scuffs are isolated to `UNCLAIMED_PREEXISTING_DAMAGE`. |
| **Camera Zoom "Cheat Codes"** | Holding a camera 5 cm from a 2 cm scratch makes it look like the entire panel is destroyed. | **Intersection over Part ($\text{IoP}$)**: Damage area is divided by the host panel area ($\text{IoP} = \text{Area}(D \cap P)/\text{Area}(P)$), automatically normalizing for camera angle and zoom distance. |
| **Financial Hallucination** | Prompting an LLM to "estimate repair costs" results in wild variances, arithmetic errors, and prompt injections (*"I am a student, pay ₹50,000"*). | **Zero-AI Actuarial Pricing Engine**: 100% deterministic Python and PostgreSQL engine executing exact IRDAI depreciation schedules, scrap salvage, and OEM part schedules. |
| **Glare & Dirt False Positives** | Neural networks mistake sunlight glints, bird droppings, or chalk lines for deep metal creases. | **Set-of-Marks (SoM) VLM Forensic Gate**: Generates bounded damage crops and queries Gemini 2.5 Flash (`temp=0.0`) in strict JSON mode to confirm physical depth, rust, and glare filtering. |
| **Double-Dipping Fraud** | Claimants re-claim prior unrepaired dents on new policies. | **Prior Claims Ledger Grounding**: Automatically queries policy claim history to reject re-claimed damage panels (`ESC-03_DOUBLE_DIPPING`). |

---

## 🏗️ End-to-End System Architecture

Auto-Settle AI is built as a **cost-cascaded architecture**—lightweight, non-GPU heuristics reject invalid or fraudulent media in milliseconds before activating deep learning models:

```mermaid
flowchart TD
    subgraph S0["Stage 0: Fast-Fail Gate (< 250ms)"]
        A[/"Walkaround Video OR 3–6 Photo Pack + Claimant Narrative"/] --> B1["Container Forensics\n(SHA-256 Dedupe, Magic Bytes, Resolution)"]
        B1 --> B2["NLE Blacklist Check\n(Rejects CapCut, Premiere, InShot, DaVinci)"]
        B2 --> B3["Visual Quality Check\n(Laplacian Sharpness >= 60, YUV Luminance [45, 235])"]
    end

    subgraph S1["Stage 1: Identity & Continuity (< 1.5s)"]
        B3 --> C{"Modality?"}
        C -- "Video" --> D1["Zero-GPU Cut Detector\n(PySceneDetect + 160-bin HSV + SSIM)"]
        D1 --> D2["ByteTrack Orbit Continuity\n(Vehicle Trajectory & Re-ID Tracking)"]
        C -- "Photo Pack" --> D3["Canonical View Triangulation\n(ANPR Plate + CIELAB Paint Grounding)"]
        D2 & D3 --> D4["Stage 2 Keyframe Portfolio"]
    end

    subgraph Intent["System 1: NLP Intent Grounding (< 7ms)"]
        A -.-> E1["Text: 'Reversing into pillar scratched rear bumper'"]
        E1 --> E2["FastEmbed ONNX (MiniLM-L6-v2)\n+ Directional Modifiers"]
        E2 --> E3["Dynamic Taxonomy Matching\n(Grounded Parts & Damage Types)"]
    end

    subgraph S2["Stage 2: Conditioned Dual-Mask Segmentation (< 850ms)"]
        D4 & E3 --> F1["Dual YOLO Segmentation\n(carparts-yolo11n-seg.pt + cardd-yolov8s-seg.pt)"]
        F1 --> F2["Shapely C-GEOS Engine\n(Pixel-Level IoP Intersection over Part)"]
        F2 --> F3{"Matches Claim Intent?"}
        F3 -- "Yes" --> G1["Billed Claim Defects\n(Admitted to Repair Schedule & SoM Crops)"]
        F3 -- "Unclaimed Wear" --> G2["Quarantined Pre-Existing Damage\n(Bypasses Multi-Panel ESC-05 Alarms)"]
        F3 -- "Declared Damage Missing" --> G3["ESC-07 Claimed Damage Not Found\n(Desk Adjuster Escalation)"]
    end

    subgraph S3to6["Stages 3 to 6: Downstream Valuation & Settlement"]
        G1 --> H1["Stage 3: Set-of-Marks VLM Depth & Rust Gate\n(Physical L1–L5 Depth, Rust Fraud ESC-04, Glare Rejection)"]
        H1 --> H2["Stage 4: Actuarial Pricing Engine & NCB Advisor\n(Deterministic OEM Catalogue, Depreciation, Deductibles)"]
        H2 --> H3["Stage 5: Bounded Negotiation Chatbot FSM\n(HMAC-SHA256 Signed Offer Cards, Concession Scheduler)"]
        H3 --> H4["Stage 6: Settlement Router & Cryptographic Voucher\n(Instant UPI Cash Transfer, PDF Surveyor Dossier)"]
    end

    style S0 fill:#0f172a,stroke:#38bdf8,color:#f8fafc
    style S1 fill:#1e293b,stroke:#38bdf8,color:#f8fafc
    style Intent fill:#1e293b,stroke:#a855f7,color:#f8fafc
    style S2 fill:#1e293b,stroke:#818cf8,color:#f8fafc
    style S3to6 fill:#0f172a,stroke:#34d399,color:#f8fafc
```

---

## 🔬 Key Engineering Innovations

### 1. Conditioned Damage Quarantine Engine
Traditional computer vision algorithms detect all scratches on a vehicle. If an older car has stone chips on the hood, door dings, and bumper scuffs, a naive model flags "multiple panel damage" and accuses the user of multi-accident fraud (`ESC-05`).
- **Our Approach**: Real-time System 1 NLP extracts declared parts. Detected damages matching user intent become **Billed Items**. Other detected defects are automatically assigned to `UNCLAIMED_PREEXISTING_DAMAGE`.
- **Result**: The claimant receives an accurate quote for their accident without being penalized for older road wear.

### 2. Scale-Invariant Geometric Normalization ($\text{IoP}$)
Holding a smartphone camera 5 cm away from a minor scratch makes it occupy 80% of the camera frame.
- **Our Approach**: Implemented in [`PolygonIntersectionEngine`](app/domain/dual_mask_segmentation/polygon_intersection_engine.py) using Shapely 2.0 C-GEOS:
  $$\text{IoP} = \frac{\text{Area}(\text{Damage} \cap \text{Part})}{\text{Area}(\text{Part})}$$
- **Anti-Zoom Inflation Defense**: If a part touches the frame border within 15 pixels, `is_complete_panel` is set to `False`, locking the IoP calculation to the unclipped wide shot and preventing camera zoom cheating.

### 3. Continuous Video Trajectory with 90.38% ID Switch Reduction
- Unbroken 360° walkarounds are tracked using Ultralytics ByteTrack. On fast panning, camera shake, and specular reflections, naive trackers lose track of the car.
- Auto-Settle AI implements an **Occlusion Re-ID Engine** with C4 RoIAlign feature extraction and Hungarian cosine gallery matching, slashing track fragmentation by **90.38%** (from 52 raw ByteTrack tracklets down to 5 persistent damage candidates).

### 4. Zero-AI Actuarial Pricing Engine
- No LLM ever touches financial numbers.
- Implements exact Indian Motor Tariff (IRDAI) rules:
  - **Material-Specific Rates**: Rubber/Nylon/Plastic at 50% depreciation; Glass at 0%; Fiberglass at 30%.
  - **Metal Age Schedules**: Scales from 0% (Year 1) to 50% (> 10 years).
  - **Adjacent Panel Paint Blending Discount**: Automatically applies a 25% discount to adjacent refinish operations.
  - **No-Claim Bonus (NCB) Preservation**: Compares net claim payout against future NCB premium loss and warns claimants when filing would result in a net financial loss.

### 5. Cryptographic Settlement Offer Cards (HMAC-SHA256)
- Negotiation offers sent to the frontend are cryptographically sealed with `HMAC-SHA256(claim_id, counter_offer_paisa, turn_number)`.
- If a claimant tampers with client-side state in DevTools, the backend signature verification fails and immediately escalates the claim (`ESC-08`).

---

## 📊 Rigorous Benchmark Evaluations (100% Pass Rate)

Auto-Settle AI is verified against a canonical benchmark suite of **20 stress scenarios** defined in [`evals/curated_test_manifest.json`](evals/curated_test_manifest.json), comprising 18 video walkarounds and 2 structured photo packs.

### Real Scenario Benchmark Scorecard
Verified from [`evals/eval_report_latest.json`](evals/eval_report_latest.json):

| Scenario ID | Test Scenario | Modality | Stage 0 | Stage 1 | Stage 2 Status | Billed Parts | Verdict |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `SC-01` | Right Flank Key Scratch | Video | 151.3 ms | 6,373.6 ms | `STAGE_3_VLM_INSPECTION` | `back_right_door`, `front_right_door` | **PASS** |
| `SC-02` | Identity Mismatch (White Car vs Blue Policy) | Video | 98.6 ms | 3,708.6 ms | **Blocked: `ESC-01`** | — | **PASS** |
| `SC-03` | Driver Flank Sideswipe Scratch | Video | 101.0 ms | 1,969.3 ms | `STAGE_3_VLM_INSPECTION` | `front_right_door` | **PASS** |
| `SC-04` | Multi-Panel Flank Sideswipe | Video | 104.9 ms | 1,979.8 ms | `STAGE_3_VLM_INSPECTION` | `back_right_door`, `front_right_door` | **PASS** |
| `SC-05` | Phantom Damage: Rear Lamp & Bumper | Video | 99.5 ms | 1,965.1 ms | **Escalated: `ESC-07`** | — | **PASS** |
| `SC-06` | Phantom Damage: Broken Wing Mirror | Video | 96.2 ms | 1,971.9 ms | **Escalated: `ESC-07`** | — | **PASS** |
| `SC-07` | Phantom Damage: Hood Hail Dent | Video | 95.0 ms | 1,967.2 ms | **Escalated: `ESC-07`** | — | **PASS** |
| `SC-08` | Phantom Damage: Bumper Crush | Video | 96.9 ms | 1,933.9 ms | **Escalated: `ESC-07`** | — | **PASS** |
| `SC-09` | Reverse Walkaround (Rear Start) | Video | 530.4 ms | 17,894.5 ms | `STAGE_3_VLM_INSPECTION` | `back_bumper` | **PASS** |
| `SC-10` | Crowded Parking Lot Occlusion | Video | 600.8 ms | 21,808.9 ms | **Escalated: `ESC-07`** | — | **PASS** |
| `SC-11` | Macro Close-Up Zoom (No Plate Visible) | Video | 440.0 ms | 2,489.8 ms | **Blocked: `ESC-02`** | — | **PASS** |
| `SC-12` | Overcast to Tree Canopy Shadow Glare | Video | 521.4 ms | 13,335.1 ms | **Escalated: `ESC-06`** | — | **PASS** |
| `SC-13` | Pre-existing Wear Quarantine | Video | 102.2 ms | 2,785.1 ms | `STAGE_3_VLM_INSPECTION` | `front_right_door` | **PASS** |
| `SC-14` | Undamaged Vehicle Negative Control | Video | 612.0 ms | 17,409.4 ms | **Escalated: `ESC-07`** | — | **PASS** |
| `SC-15` | Opposite-Side Fraud Attempt | Video | 97.8 ms | 2,038.1 ms | **Escalated: `ESC-07`** | — | **PASS** |
| `SC-16` | Faint Scratch vs Reflection Glare | Video | 451.0 ms | 12,471.6 ms | **Escalated: `ESC-07`** | — | **PASS** |
| `SC-17` | Low-Light Basement Parking | Video | **82.5 ms** | N/A | **Blocked: `QUALITY_GATE`** | — | **PASS** |
| `SC-18` | High-Speed Corner Whip-Pan | Video | 539.1 ms | 14,263.9 ms | `STAGE_3_VLM_INSPECTION` | `front_bumper` | **PASS** |
| `SC-19` | Photo Pack: Unproven Door Scratch | Photo | 85.3 ms | 159.4 ms | **Escalated: `ESC-07`** | — | **PASS** |
| `SC-20` | Photo Pack: Unproven Lamp & Bumper | Photo | 112.1 ms | 153.2 ms | **Escalated: `ESC-07`** | — | **PASS** |

### Benchmark Latency Metrics
- **Stage 0 (Fast-Fail Gate)**: Average **250.9 ms** (Fast rejection of corrupt media in 82.5 ms).
- **System 1 (Intent Grounding)**: Average **6.7 ms** (FastEmbed ONNX CPU inference).
- **Stage 2 (Dual-Mask Segmentation)**: Average **858.8 ms** (Dual YOLO inference + Shapely polygon topology).
- **Stage 1 (Identity & Continuity)**: Average **6,667.3 ms** on full 30 FPS walkarounds; **153 ms** on photo packs.

### Authentic Dataset Corpus (Zero Synthetic Slices)
Cataloged in [`test_assets/videos/manifest.json`](test_assets/videos/manifest.json):
- **35 Total Authentic Walkaround Videos** (741.29 MB total):
  - `simple/` (25 videos, 582.9 MB): Clean daylight orbits, single vehicles, smooth camera paths.
  - `difficult/` (10 videos, 158.4 MB): Severe crashes, macro zooms, crowded parking lots, overcast lighting, tree canopy shadows.
- **MOT Challenge RTDETR-VD Dataset**: 5,424 annotated vehicle damage tracking frames across 9 benchmark sequences.

---

## 📁 Repository Structure

```
settle_ai/
├── app/                          # Core production application code
│   ├── api/                      # FastAPI endpoints (claims, audit, negotiation, SSE streaming)
│   ├── core/                     # Logging, telemetry, config settings, and security
│   ├── domain/                   # Pure business logic by pipeline stage
│   │   ├── fast_fail_gate/       # Stage 0: Forensics, container validation, visual quality
│   │   ├── vehicle_identity/     # Stage 1: Plate OCR, color distance, cut detector, tracking
│   │   ├── claim_intent/         # System 1: FastEmbed ONNX NLP intent grounder
│   │   ├── dual_mask_segmentation/# Stage 2: Dual YOLO + Shapely IoP damage quarantine
│   │   ├── vlm_damage_inspection/# Stage 3: Set-of-Marks crop engine, depth grading, rust gate
│   │   ├── actuarial_pricing/    # Stage 4: Deterministic OEM parts math, NCB advisor
│   │   ├── negotiation_chatbot/  # Stage 5: Bounded FSM negotiation, HMAC offer signing
│   │   └── settlement_escalation/# Stage 6: Settlement router, UPI vouchers, PDF dossiers
│   └── infrastructure/           # Database, Redis pub/sub, external model adapters
├── docs/                         # Specifications, LLDs, adversarial reports, and presentation
│   ├── README.md                 # Documentation directory index
│   ├── presentation/             # Executive presentation slide deck (PPTX)
│   └── lld/                      # Stage-by-stage Low-Level Design documents
├── evals/                        # Evaluation harnesses and testbench
│   ├── README.md                 # Evaluation suite guide & instructions
│   ├── comprehensive_harness.py  # Master evaluation engine (Stages 0–6)
│   ├── eval_harness.py           # Canonical 20-scenario benchmark runner
│   ├── web_testbench.py          # Standalone visual browser testbench GUI (Port 8080)
│   └── curated_test_manifest.json# Manifest defining the 20 benchmark scenarios
├── frontend/                     # Modern claims workstation browser UI
│   ├── README.md                 # Frontend documentation
│   ├── index.html                # Editorial responsive claims desk
│   └── src/                      # Vanilla JS and CSS (Dark Mode, Video Switcher, NLP parser)
├── scripts/                      # Utility scripts (training, data extraction, presentation builds)
│   └── README.md                 # Scripts documentation
├── test_assets/                  # Curated authentic video datasets and keyframes
│   └── videos/                   # 35 authentic walkaround videos (simple/ and difficult/)
├── tests/                        # 494 automated pytest unit, integration, and E2E tests
├── weights/                      # YOLO model weights (Carparts, CarDD, YOLO11m)
├── docker-compose.yml            # PostgreSQL 16, Redis 7, MinIO container stack
├── pyproject.toml                # uv / PEP 621 dependency specification
└── README.md                     # Project overview and judge guide
```

---

## 🚀 Quickstart & Demo Walkthrough

### 1. Prerequisites
- Python 3.12+ (managed with `uv`)
- Optional: CUDA-capable GPU (NVIDIA RTX 3060/4060 or better; falls back gracefully to CPU)

### 2. Setup & Installation
```bash
# Clone the repository
git clone https://github.com/idkjashan/settle_ai.git
cd settle_ai

# Install dependencies with uv
uv sync
```

### 3. Launch the Unified Claims Workstation
FastAPI serves both the backend REST API and the live frontend desk:
```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open your browser to:
- **Workstation UI**: `http://127.0.0.1:8000/`
- **Interactive Swagger Docs**: `http://127.0.0.1:8000/docs`

### 4. Run the 20-Scenario Benchmark Runner
Verify that all 20 stress scenarios pass deterministically:
```bash
uv run python evals/eval_harness.py
```

### 5. Launch the Visual Web Testbench
To visually inspect intermediate YOLO segmentation masks and Set-of-Marks crops in a browser:
```bash
uv run python evals/web_testbench.py
```
Then visit `http://127.0.0.1:8080/`.

---

## 🧪 Automated Test Suite (494 Tests)

Run the automated test suite across all 12 domain layers:
```bash
uv run pytest
```

### Test Coverage Breakdown
| Domain Test Suite | Tests | Primary Verification Focus |
| :--- | :---: | :--- |
| **Actuarial Pricing** (`tests/actuarial_pricing/`) | **102** | IRDAI depreciation, material rates, salvage deduction, compulsory excess, NCB preservation |
| **VLM Damage Inspection** (`tests/vlm_damage_inspection/`) | **94** | Tri-stream prompt engine, Set-of-Marks crops, L1–L5 depth grading, rust fraud (`ESC-04`) |
| **Negotiation Chatbot** (`tests/negotiation_chatbot/`) | **51** | FSM concession curves, HMAC-SHA256 signature tampering, counter-offer bounds |
| **Dual-Mask Segmentation** (`tests/dual_mask_segmentation/`) | **41** | Shapely IoP geometry, zoom anti-inflation, part candidate matching, Carparts + CarDD YOLO |
| **Settlement & Escalation** (`tests/settlement_escalation/`) | **35** | Instant UPI voucher generation, surveyor dossier assembly, PDF generation, penny balancing |
| **Perception & Tracking** (`tests/perception/`) | **32** | Occlusion Re-ID tracking, C4 RoIAlign feature extraction, Hungarian cosine matching |
| **Fast-Fail Gate** (`tests/fast_fail_gate/`) | **28** | Container validation, NLE blacklist, Laplacian blur threshold, luminance bounds |
| **System 1 Intent Grounding** (`tests/claim_intent/`) | **23** | FastEmbed ONNX token extraction, directional modifier parsing, taxonomy resolution |
| **Vehicle Continuity** (`tests/vehicle_identity_continuity/`) | **23** | ANPR OCR homoglyph matching, CIELAB paint distance $\Delta E$, zero-GPU cut detection |
| **Real Scenario Walkarounds** (`tests/test_scenarios_break.py`) | **17** | Stress testing real walkaround videos (collision, macro zoom, crowded lot, reverse orbit) |
| **Adversarial & Tamper** (`tests/adversarial/`) | **13** | Video splices, spoofed metadata, digital glare injection, duplicate claim prevention |
| **Dataset Integrity** (`tests/test_rtdetr_vd_dataset.py`) | **13** | MOT Challenge dataset structure, bounding box decodability, seqinfo verification |
| **API & Evaluation Infrastructure** (`tests/api/`, `tests/evals/`) | **22** | FastAPI routes, SSE streaming, master evaluation harness, stage bypassing |
| **TOTAL** | **494** | **100% Comprehensive Domain Test Coverage** |

---

## 📜 License & Compliance

Distributed under the **MIT License**. Compliant with IRDAI motor insurance estimation guidelines, standard ISO 27001 audit trail specifications, and OWASP API security practices.
