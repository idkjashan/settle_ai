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
- [x] **Milestone 7: Multi-Subagent Audit, Adversarial Hardening & Real Dataset Verification**
  - [x] Subagent 1 (Dataset Engineer): Acquired, standardized (1080p, 15-21s, H.264), and indexed real car walkaround videos (`toyota_hilux_white_ute.mp4`, `fiat_500_blue_hatchback.mp4`, `vw_golf_grey_hatchback.mp4`, `ferrari_360_silver_coupe.mp4`) in `test_assets/real_videos/manifest.json`.
  - [x] Subagent 2 (Code Auditor): Identified 10 structural failure modes, missing test coverage, and memory/disk leakage paths.
  - [x] Subagent 3 (Adversarial Tester): Engineered red-team test suite (`tests/adversarial/test_adversarial_break.py`), reproducing 11 critical edge cases (0-frame bypass, scratch leak, lock release race, degenerate bboxes, ffprobe null tags, quorum bypass, zombie claims).
  - [x] Subagent 4 (Verifier & Pragmatic Fixer): Implemented minimal Ponytail fixes across 9 files (+165 / -45 lines):
    - Added minimum 15-frame continuity threshold to Gate 1 `CutDetector`.
    - Added deterministic RAII `finally:` scratch video cleanup in background pipeline and orchestrator.
    - Serialized in-flight Redis lock release *after* PostgreSQL claim commit (eliminating TOCTOU deduplication bypass).
    - Clamped ROI coordinates in `ColorGroundingValidator` and `PlateOCRValidator` to prevent OpenCV empty-source assertions and negative slicing.
    - Handled null tags and non-numeric dimensions gracefully in `ContainerForensicsValidator`.
    - Enforced mandatory sample quorum in `VisualQualityValidator` to reject truncated video containers.
    - Aligned `LUMINANCE_MAX_THRESHOLD` to 220.0 to reject overexposed videos.
    - Guaranteed database error state transitions (`REJECTED_STAGE1_ERROR` / `ESC-02`) and SSE emission on pipeline exceptions.
    - Cleared PyTorch CUDA cache (`torch.cuda.empty_cache()`) in Stage 1 `finally:` block.
    - Integrated real vehicle walkaround test suite (`tests/test_real_videos.py`).
  - [x] Unified Full Suite: **51 / 51 tests PASSED (100% pass rate in ~60s)**.
- [x] **Milestone 8: Scenario Stress-Testing, Keyframe Isolation & Breaker Suite**
  - [x] Subagent B (Scenario Stress-Tester & Breaker):
    - Synthesized 6 realistic 720p 15.0s scenario walkaround videos in `test_assets/scenario_videos/`:
      * `scenario_01_walkaround_damaged_scratch.mp4`: Walkaround with realistic door panel key scratch damage.
      * `scenario_02_closeup_zoom_damaged_panel.mp4`: Closeup zoom into door scratch panel exceeding `CLOSEUP_ZOOM_AREA_RATIO >= 0.50` into macro view.
      * `scenario_03_reverse_walkaround_side_rear_first.mp4`: Reverse walkaround starting on rear/side before showing front plate.
      * `scenario_04_parking_lot_multicar_background.mp4`: Crowded dealership parking lot with adjacent background cars.
      * `scenario_05_outdoor_lighting_variation.mp4`: Dynamic sunlight glare to deep canopy shadow transitions with specular glare penalty.
      * `scenario_06_fast_pan_corner_whip.mp4`: Rapid rotational corner whip-panning.
    - Isolated and extracted canonical keyframes (`front_bumper.jpg`, `side_body_panel.jpg`, `damage_closeup_primary.jpg`) across all 10 scenarios (6 scenarios + 4 real videos) in `test_assets/keyframes_for_stage2/<scenario_id>/`, measuring Laplacian sharpness (>= 80) and specular glare ratios.
    - Identified and isolated 5 scenario-level breakages and edge cases in `tests/test_scenarios_break.py`:
      1. *Fast Corner Pan Cut False Positive*: `CutDetector` triggers `S1_CUT_PYSCENEDETECT_TRIGGER` during fast camera corner panning.
      2. *Multi-Car Target Latching Failure*: `ObjectTracker` naively selects first detected car box instead of primary vehicle, causing track loss on real parking lots (`fiat_500` and `hilux`).
      3. *Reverse Walkaround Missing Late Plate OCR*: `PlateOCRValidator` defers plate to late track, but tracker never runs OCR, failing claim on `S1_PLATE_NOT_FOUND_OR_UNREADABLE`.
      4. *Reverse Walkaround Keyframe Misassignment*: `rel_t <= 0.35` timeline heuristic assigns rear/side frames as `front_bumper.jpg`.
      5. *Wide Shot Minimum Area Disqualification*: `MIN_VEHICLE_AREA_RATIO = 0.12` rejects wide walkaround shots (e.g. Hilux at 0.076), falsely triggering `S1_NO_VEHICLE_DETECTED`.
    - Executed scenario test suite: **12 / 12 tests PASSED (100% pass rate in 30.27s)**.
    - Unified Full Suite: **63 / 63 tests PASSED (100% pass rate in 87.19s)**.
  - [x] Subagent C (Independent Pragmatic Fixer):
    - Executed user directive: Purged all synthetic videos and transitioned to 100% real online YouTube walkarounds (`scenario_01_damaged_collision.mp4`, `scenario_02_macro_closeup_scratch.mp4`, `scenario_03_parking_lot_multicar.mp4`, `scenario_04_reverse_walkaround_rear_start.mp4`, `scenario_05_challenging_lighting_overcast_canopy.mp4`).
    - Resolved all 5 systemic breakages via the Ponytail 7-Rung Decision Ladder:
      1. *Target Vehicle Latching in Multi-Car / Parking Lot Scenes* (`object_tracker.py`): Foreground candidate selection using `max(box_area)` meeting `MIN_VEHICLE_AREA_RATIO`. Latches target track ID to primary claim vehicle (e.g. Fiat 500 track ID 2 instead of background car ID 1), completely eliminating track loss.
      2. *CutDetector False Positives on Fast Corner Pans* (`cut_detector.py`): Requires both `delta_hsv >= 27.0` AND histogram correlation collapse (`corr < 0.70`) before flagging hard scene cuts, preventing whip-pan false rejects while preserving cut detection priority.
      3. *Late-Track Plate OCR Grounding on Reverse Walkarounds* (`object_tracker.py`, `plate_ocr_validator.py`, `orchestrator.py`): Strided bumper ROI OCR verification during tracking when plate is deferred, successfully validating `CJ09025` at frame 210 with homoglyph cost 0.25 and updating claim telemetry.
      4. *Plate Validator Minimum Vehicle Area Ratio* (`config.py`): Adjusted `MIN_VEHICLE_AREA_RATIO = 0.06` (from 0.12), enabling initial-window verification of wide exterior walkaround frames (e.g. Hilux at 7.6% area ratio).
      5. *Dynamic Keyframe View Anchoring on Reverse Walkarounds* (`object_tracker.py`): Front bumper keyframe is dynamically anchored to the plate verification frame window rather than hardcoded early timeline (`rel_t <= 0.35`). Ensured canonical keyframes (`front_bumper`, `side_body_panel`, `damage_closeup_primary`) are guaranteed extracted for every valid video into `test_assets/keyframes_for_stage2/<scenario_id>/`.
    - Executed full pytest suite: **63 / 63 tests PASSED (100% green in 107.26s)**.
- [x] **Milestone 9: Deep Pipeline Hardening & Heuristic Fragility Remediation**
  - [x] Subagent D (Keyframe Perspective Engineer):
    - Replaced hardcoded keyframe counts and rigid timeline windows ($t \le 0.33$, $0.33 < t \le 0.67$) with **Adaptive Trajectory Quality Curation** ($\approx 1$ frame per second of walkaround, bounded $[8, 30]$).
    - Guaranteed 100% distinct canonical aliases (`front_bumper.jpg`, `side_body_panel.jpg`, `damage_closeup_primary.jpg`) across all 9 real videos (zero duplicate MD5 hashes).
  - [x] Subagent E (Pipeline Hardening Engineer):
    - Resolved 6 concrete heuristic fragilities across Stage 0 and Stage 1:
      1. *Multi-word Color Keyword Normalization* (`color_grounding_validator.py`): Extract canonical color keywords (`WHITE`, `BLACK`, `SILVER`, `GREY`, `GRAY`, `RED`, `BLUE`, `GREEN`, `YELLOW`, `ORANGE`, `BROWN`) from policy registry strings (e.g. "Metallic Blue" $\to$ "BLUE") before evaluation.
      2. *Black Vehicle Daylight Reflection Tolerance* (`color_grounding_validator.py`): Scaled `BLACK` bounds to $S \le 45$, $V \le 100$ to accommodate glossy clearcoat reflections under open daylight.
      3. *Plate OCR Length Floor & Structural Regex Prioritization* (`plate_ocr_validator.py`): Lowered plate candidate floor to $\ge 5$ characters and enforced structural regex validation (Indian HSRP `^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{4}$`, BH `^[0-9]{2}BH[0-9]{4}[A-Z]{1,2}$`, and generic UK/AU/US `^(?=.*[A-Z])(?=.*[0-9])[A-Z0-9]{5,10}$`) to prioritize genuine plates over short brand badges ("TURBO", "HYUNDAI").
      4. *Foreground Target Selection & Multi-Frame IoU Persistence* (`plate_ocr_validator.py`): Added multi-frame candidate IoU tracking ($\ge 0.35$) across initial window samples, selecting persistent stationary vehicle candidates ($\ge 2$ hits) with largest bounding box area.
      5. *Late-Track Color Grounding Enforcement* (`orchestrator.py`): Enforced paint color validation on the late-verified vehicle anchor for reverse walkarounds before claim approval.
      6. *FPS-Scaled Freeze Frame Threshold* (`cut_detector.py`): Replaced static 15-frame freeze count with frame-rate scaled threshold `max(15, int(fps * 0.75))` (750ms minimum pause).
  - [x] Full Pytest Suite: **69 / 69 tests PASSED (100% green in 114.16s)**.

---

## 5. Test Execution & Verification Log
- **Stage 0 Suite (`tests/fast_fail_gate/`)**: 15 tests | Passed: 15 (100%)
- **Stage 1 Suite (`tests/vehicle_identity_continuity/`)**: 18 tests | Passed: 18 (100%)
- **Adversarial Red-Team Suite (`tests/adversarial/`)**: 13 tests | Passed: 13 (100%)
- **Real Vehicle Walkaround Suite (`tests/test_real_videos.py`)**: 5 tests | Passed: 5 (100%)
- **Scenario Stress & Hardening Suite (`tests/test_scenarios_break.py`)**: 18 tests | Passed: 18 (100%)
- **Unified Full Suite (`tests/`)**:
  - Command: `/home/jashan/settleai/.venv/bin/pytest -v tests/`
  - Total Tests: 69 | Passed: 69 (100%) | Failed: 0
