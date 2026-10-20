# Auto-Settle AI — Implementation Progress & Architecture Ledger

## 1. Project Overview & Orchestration Mandate
- **System**: Auto-Settle AI (Autonomous Video-to-Cash Claims Adjuster)
- **Runtime Stack**: Python 3.12 (`uv`), FastAPI, PostgreSQL 16, Redis 7, MinIO/S3, Ultralytics YOLO11 (`yolo11m-seg`), EasyOCR (CUDA) / VLM Fallback, PySceneDetect, OpenCV, Shapely, PyTorch 2.6 FP16 + CUDA.
- **Hardware**: NVIDIA GeForce RTX 4060 Laptop GPU (8GB VRAM), WSL Linux.
- **Mandate**: Orchestrate full implementation of the stack, Stage 0 (Fast-Fail Gate), and Stage 1 (Vehicle Identity & Continuity Grounding), utilizing fresh subagents for independent test creation and validation.

---

## 2. Inconsistency Reconciliations Between Documents
| Topic | Document Discrepancy | Settle / Reconciled Decision |
| :--- | :--- | :--- |
| **Video Duration Gate** | HLD mentions `5s-45s` optimal and `5s-60s` limit in different sections. | Hard rejection gate is strictly `5.0s <= duration <= 60.0s`. Optimal user guidance remains 15s walkaround ($5\text{--}45\text{s}$). |
| **Optical Flow vs SSIM & Histogram** | HLD draft suggested optical flow RANSAC; LLD Stage 1 notes this fails on textureless glossy car paint. | Reconciled to **$8\times8$ Block SSIM + $4\times4$ Spatial Grid HSV Correlation + PySceneDetect** for robust zero-GPU cut detection. |
| **Model Residency in Stage 1** | Early plan loaded `Carparts-Seg` in Stage 1; LLD Stage 1 notes VRAM constraint ($\le 1536\text{ MB}$). | Stage 1 strictly runs `yolo11m-seg.pt` (vehicle segmentation + ByteTrack) + CUDA OCR. `Carparts-Seg` is deferred to Stage 2 (`dual_mask_segmentation`). |
| **Subprocess Tools** | `ffprobe`/`ffmpeg` system package vs portable. | Configured portable static `ffmpeg`/`ffprobe` in `~/.local/bin` to ensure deterministic execution in user space without requiring interactive sudo. |

---

## 3. Explicit Diversions from HLD / LLD
| Diversion ID | Source Document | Implemented Mechanism | Rationale / Upgrade Path |
| :--- | :--- | :--- | :--- |
| *DIV-01* | `LLD_STAGE_0` | Static ffmpeg/ffprobe binaries in `~/.local/bin` | Running in non-root WSL environment where interactive sudo is restricted. `static-ffmpeg` provides bit-for-bit identical v8.0 binaries. |
| *DIV-02* | `LLD_STAGE_1` | EasyOCR on CUDA in place of PaddleOCR | Seamless native integration with PyTorch 2.6+CUDA 12.4 virtualenv; implements the identical homoglyph-weighted Levenshtein distance ($D_w$) and 2-line Indian HSRP merge rules. |
| *DIV-03* | `LLD_STAGE_1` | Real photographic vehicle frames (`test_assets/`) for synthetic test videos | Synthetic geometric canvas drawings (simple rectangles) are rejected by deep-CNN vision models (`yolo11m-seg`). Compositing photorealistic Hyundai Venue frames ensures true CNN feature detection with 0.94+ confidence. |

---

## 4. Milestone Progress Tracker
- [x] **Milestone 1: Environment & Foundation Stack Setup**
  - [x] Python 3.12 virtualenv via `uv`
  - [x] Static `ffmpeg` and `ffprobe` in `~/.local/bin`
  - [x] Docker Compose (PostgreSQL 16, Redis 7) running and healthy
  - [x] PyTorch 2.6.0+cu124 with CUDA support verified on NVIDIA GeForce RTX 4060 Laptop GPU
  - [x] Ultralytics YOLO11 (`yolo11m-seg.pt`) downloaded and pre-warmed on CUDA in `weights/`
  - [x] EasyOCR installed and verified on CUDA
- [x] **Milestone 2: Database Layer & Core Infrastructure**
  - [x] SQLAlchemy 2.0 Async declarative models (`InsuredPolicy`, `Claim`, `OemPart`, `UnrepairedClaim`) with partial unique indexes
  - [x] Async session factory with `NullPool` & repository classes (`PolicyRepository`, `ClaimRepository`, `OemRepository`, `UnrepairedClaimsRepository`, `DemoResetRepository`)
  - [x] Database seeder executed with test policies (`POL-HAPPY-001`, `POL-EXPIRED-002`, `POL-FUTURE-003`, `POL-CLAIMCAP-004`, `POL-CANCELLED-005`, `POL-RED-007`) and Hyundai Creta OEM parts catalogue
  - [x] Redis atomic in-flight locking (`SET NX EX 60`), pub/sub event publisher for SSE, and demo reset flush
  - [x] Bounded scratch ingest streaming service (`/tmp/autosettle_ingest`) with on-the-fly SHA-256 and RAII lease cleanup
  - [x] S3/Local persistent storage client
- [x] **Milestone 3: Stage 0 (Fast-Fail Gate) Implementation & Verification**
  - [x] `app/domain/fast_fail_gate/schemas.py` and `interfaces.py`
  - [x] `policy_dedupe_gate.py`: Tier-1 SQL policy validation & historical video duplicate check with demo rehearsal bypass
  - [x] `container_forensics.py`: Tier-2A sandboxed ffprobe validator (resolution >= 720p, duration 5s-60s, fps >= 15, NLE editor tag blacklist with standard encoder whitelist)
  - [x] `visual_quality_gate.py`: Tier-2B single-pass OpenCV 5-frame grab() scan with YUV luminance [45, 235] and 720p-normalized Laplacian sharpness >= 80
  - [x] `remediation_mapper.py`: Actionable UX directives mapper
  - [x] `orchestrator.py`: FastFailGateOrchestrator coordinating Tier-1 short-circuit and Tier-2 threadpool forensics
  - [x] API endpoints: `POST /api/v1/claims/upload`, `GET /claims/{id}`, `GET /claims/{id}/events` (SSE), `POST /api/v1/demo/reset`
  - [x] **Stage 0 Independent Verification**: 15 / 15 tests PASSED (100% pass rate in 31.64s) by independent test subagent
- [x] **Milestone 4: Stage 1 (Vehicle Identity & Continuity) Implementation**
  - [x] `app/domain/vehicle_identity_continuity/schemas.py`, `config.py`, `interfaces.py`, `exceptions.py`
  - [x] `cut_detector.py`: Gate 1 fast CPU cut & splice firewall (< 100ms) with downsampled 320x180 decode, 160-bin HSV histogram correlation (r < 0.60), ContentDetector (score >= 27.0), 4x4 spatial grid correlation (p25 < 0.52), 8x8 block SSIM (< 0.68), and freeze-frame detection (> 15 frames)
  - [x] `plate_ocr_validator.py`: Gate 2A/B progressive ANPR grounding with YOLO11m-seg vehicle detection, spatial prior bumper zone filtering, 2-line Indian HSRP plate merging, homoglyph-weighted Levenshtein distance, and two-phase discovery
  - [x] `color_grounding_validator.py`: Gate 2C dominant body paint grounding with tire/glass/shadow filtering, circular mean Hue, median Saturation/Value, and circular distance matching (delta E <= 35.0)
  - [x] `object_tracker.py` & `keyframe_selector.py`: Gate 3 reset-safe strided ByteTrack (`vid_stride=3`), closeup zoom hand-off forgiving macro panel dropout, inline rolling Top-K keyframe extraction (Laplacian sharpness - specular glare penalty), and atomic JPEG persistence
  - [x] `orchestrator.py`: VehicleIdentityContinuityOrchestrator coordinating Gate 1 -> Gate 2 -> Gate 3 with state transitions and SSE event emission
  - [x] Wired into FastAPI background pipeline task from Stage 0 upload
- [x] **Milestone 5: Video Acquisition & Stage 1 Independent Verification**
  - [x] Photographic vehicle test assets acquired in `test_assets/` (White Hyundai Venue, Blue Hyundai Venue, Tucson SUV)
  - [x] Independent subagent `Stage 1 Test Engineer` engineered test suite (`tests/vehicle_identity_continuity/`)
  - [x] All 18 Stage 1 tests verified and passing (100% pass rate in 16.81s)
- [x] **Milestone 6: End-to-End Integration & Unified Verification**
  - [x] Full test suite executed across Stage 0 and Stage 1: **33 / 33 tests PASSED (100% pass rate in 42.68s)**
  - [x] Progress and architecture divergence ledger fully updated

---

## 5. Test Execution & Verification Log
- **Stage 0 Suite (`tests/fast_fail_gate/`)**:
  - Command: `/home/jashan/settleai/.venv/bin/pytest -v tests/fast_fail_gate/`
  - Total Tests: 15 | Passed: 15 (100%) | Failed: 0
  - Coverage: T0-01, T0-05, T0-06, T0-08, T0-09, T0-11, T0-13, T0-14, T0-15, T0-16, T0-17, T0-18, T0-20, T0-21, cancelled policy.
- **Stage 1 Suite (`tests/vehicle_identity_continuity/`)**:
  - Command: `/home/jashan/settleai/.venv/bin/pytest -v tests/vehicle_identity_continuity/`
  - Total Tests: 18 | Passed: 18 (100%) | Failed: 0
  - Coverage:
    - Gate 1 (Continuous Walkaround, Hard Scene Cut, Subtle Jump Splice, Freeze-Frame Detection)
    - Gate 2 (Single-Line Plate ANPR, 2-Line HSRP Stacked Merge, Homoglyph Distance Tolerance, Mismatched Wrong Plate Rejection, Paint HSV White Match, Paint HSV Blue Mismatch)
    - Gate 3 (Strided Tracking & Keyframes Saved, Macro Closeup Zoom Hand-off, Track Lost Exceeded Rejection, Parking Lot Vehicle Switch Rejection)
    - End-to-End Orchestrator (Happy Path Claim to STAGE_2_SEGMENTATION, Cut Failure ESC-02, Wrong Plate ESC-01, Wrong Color ESC-01)
- **Unified Full Suite (`tests/`)**:
  - Command: `/home/jashan/settleai/.venv/bin/pytest -v tests/`
  - Total Tests: 33 | Passed: 33 (100%) | Failed: 0 | Duration: 42.68s
