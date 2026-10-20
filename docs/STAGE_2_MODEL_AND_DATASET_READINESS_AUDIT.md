# Auto-Settle AI — Stage 2 Model & Dataset Readiness Audit

| Document Control | Details |
| :--- | :--- |
| **Document ID** | `AUDIT-STAGE-2-MODEL-DATASET-READINESS` |
| **Date** | 2026-10-21 |
| **Status** | Complete & Verified |
| **Author** | Antigravity AI Engineering Harness |
| **Scope** | Stage 2 Dual-Mask Part & Damage Segmentation (`app/domain/dual_mask_segmentation/`) |
| **Host Environment** | Windows 11 (x64), Python 3.11.9, CPU PyTorch 2.14.1+cpu |
| **Test Verification Status** | **37 / 37 Stage 2 Tests Passing**, **5 / 5 CI Invariants Passing**, **33 / 33 Stage 0/1 Tests Passing** |

---

## 1. Executive Summary

This audit consolidates findings from an in-depth code inspection, dataset analysis, smoke test execution, and hardware readiness evaluation for **Stage 2 (Dual-Mask Part & Damage Segmentation)** of Auto-Settle AI.

### Key Conclusions:
1. **Critical Defect Resolved**: An architectural flaw that allowed Stage 2 to silently fall back to `weights/yolo11m-seg.pt` (generic 80-class COCO checkpoint) and cross-wire COCO classes (`person` $\to$ `dent`, `car` $\to$ `crack`) was completely eliminated. Strict taxonomy validation was introduced.
2. **Safe Failure Guaranteed**: When required custom model weights are missing or incompatible, the pipeline explicitly halts, transitions the claim to `REJECTED_STAGE2_ERROR` with `failure_codes=["S2_MODEL_COMPATIBILITY_ERROR"]`, and emits a `STAGE_2_FAILED` SSE event. It does not masquerade as an insured business escalation (`ESC-03`..`ESC-07`) or pass incomplete claims to Stage 3.
3. **Dataset Kit Role Clarified**: The local `stage2_edge_case_dataset_kit/` contains 111 images for **evaluation and edge-case benchmarking**, not model training. Its annotations provide bounding boxes and scenario tags, but lack fine-grained polygon segmentation coordinates (`part_masks_or_polygons: []`).
4. **Smoke Test Verification**: Running the generic COCO checkpoint on the 111 edge-case images yielded 641 generic object detections (cars, persons, trucks) and **0 vehicle damage detections**, proving that generic models cannot perform damage segmentation.
5. **No Local Weights Found**: A full system search confirmed that no custom-trained `yolo11m-cardd-seg.pt` or `yolo11m-carparts-seg.pt` checkpoints exist locally.
6. **Training Requires Cloud GPU**: The host environment utilizes Intel Iris Xe integrated graphics with CPU-only PyTorch (no CUDA). Training YOLO11m models (~20M parameters) on ~7,000 images is computationally infeasible on local CPU and must be executed on a cloud GPU (e.g., Google Colab / Kaggle free T4/A100).

---

## 2. Stage 2 Model Compatibility & Taxonomy Hardening

### 2.1 The Silent Fallback Defect
Prior to this fix, `DualMaskSegmentationOrchestrator` contained a silent fallback mechanism:
```python
# PREVIOUS DANGEROUS PATTERN (REMOVED):
if not os.path.exists(cardd_path):
    cardd_path = "weights/yolo11m-seg.pt"  # Generic COCO model!
```
Because Ultralytics YOLO models assign predictions by class index ($0, 1, 2, \dots$), passing a COCO model into the damage segmenter resulted in severe cross-wiring:
- COCO Class 0 (`person`) was mapped to CarDD Class 0 (`dent`).
- COCO Class 2 (`car`) was mapped to CarDD Class 2 (`crack`).

### 2.2 Taxonomy Validation Engine
The fix implemented `validate_model_taxonomy()` in `app/domain/dual_mask_segmentation/taxonomy.py`. It strictly validates loaded models against the project's canonical taxonomies:

```python
def validate_model_taxonomy(
    model: object,
    expected_class_map: Dict[int, str],
    model_role: str = "Model",
) -> None:
    # 1. Validates presence of model.names
    # 2. Rejects non-integer dictionary keys
    # 3. Validates contiguous integer indices (0..N-1)
    # 4. Validates exact class count equality
    # 5. Validates exact class label string matching for every ID
```

#### Canonical Class Taxonomies:
- **Carparts-Seg (`CARPARTS_CLASS_MAP` - 23 Classes)**:
  `0: back_bumper`, `1: back_door`, `2: back_glass`, `3: back_left_door`, `4: back_left_light`, `5: back_light`, `6: back_right_door`, `7: back_right_light`, `8: front_bumper`, `9: front_door`, `10: front_glass`, `11: front_left_door`, `12: front_left_light`, `13: front_light`, `14: front_right_door`, `15: front_right_light`, `16: hood`, `17: left_mirror`, `18: object` (ignored), `19: right_mirror`, `20: tailgate`, `21: trunk`, `22: wheel`.
- **CarDD Damage (`CARDD_CLASS_MAP` - 6 Classes)**:
  `0: dent`, `1: scratch`, `2: crack`, `3: glass_shatter`, `4: lamp_broken`, `5: tire_flat`.

### 2.3 Exception Hierarchy & Claim State Transitions
To guarantee clean operational monitoring, model compatibility errors are strictly separated from domain business escalations:
- `Stage2ModelCompatibilityError` inherits from `AutoSettleException` (NOT `Stage2Error`).
- In `app/api/v1/endpoints/claims_router.py`, `get_stage2_orchestrator()` is placed within a guarded `try/except` block.
- On compatibility failure:
  - Claim Status: `REJECTED_STAGE2_ERROR`
  - Stage: `STAGE_2_SEGMENTATION`
  - Escalation Code: `None` (prevents false escalation flags)
  - Failure Codes: `["S2_MODEL_COMPATIBILITY_ERROR"]`
  - SSE Event: `STAGE_2_FAILED`
- On unexpected internal exceptions:
  - Failure Codes: `["STAGE_2_INTERNAL_ERROR"]` (eliminates misleading hardcoded `ESC-07`).

---

## 3. Dataset Readiness Audit

### 3.1 `stage2_edge_case_dataset_kit/` Inspection
An inspection of the local dataset kit directory revealed the following distribution:

| Category Folder | File Count | Image Format | Typical Resolution |
| :--- | :---: | :---: | :---: |
| `subtle_damage` | 15 | JPEG | 1080p / 4K |
| `multi_vehicle` | 16 | JPEG | 1080p / 4K |
| `collision_damage` | 16 | JPEG | 1080p / 4K / 8K |
| `part_boundaries` | 16 | JPEG | 1080p / 4K |
| `occlusion` | 16 | JPEG | 1080p / 4K |
| `reflections_false_positives` | 16 | JPEG | 1080p / 4K |
| `undamaged_controls` | 16 | JPEG | 1080p / 4K |
| **Total** | **111** | **JPEG** | — |

### 3.2 Annotation Assessment
- Each image is accompanied by a JSON metadata file in `annotations/`.
- **Finding**: While bounding boxes for vehicles and damages are present, polygon segmentation masks are empty (`"part_masks_or_polygons": []`).
- **Conclusion**: This dataset kit is structured for **evaluation, edge-case benchmarking, and integration tests**, not for training deep instance segmentation models.

---

## 4. Empirical Smoke Test Findings

To verify the real-world behavior of the pipeline prior to model training, a smoke test was executed across all 111 dataset kit images using the available `weights/yolo11m-seg.pt` model.

### Quantitative Smoke Test Results:
- **Total Images Processed**: 111
- **Total Detections Generated**: 641
- **Detection Breakdown**:
  - Cars: 351
  - Persons: 164
  - Trucks: 66
  - Traffic Lights: 19
  - Motorcycles: 12
  - Busses: 9
  - Chairs: 8
  - Other COCO objects: 12
- **Vehicle Damage Detections**: **0** (0 dents, 0 scratches, 0 cracks, 0 tears)

This empirical test confirms that the generic COCO model has zero capability to detect or segment car damage, validating the necessity of custom-trained weights.

---

## 5. Hardware & Training Compute Analysis

### 5.1 Host System Profiling
- **OS**: Windows 11 Desktop (x64)
- **CPU**: Intel Core i5 / i7 processor
- **GPU**: Intel(R) Iris(R) Xe Graphics (Integrated GPU, 2GB shared VRAM)
- **Discrete GPU / CUDA**: None (`nvidia-smi` not found)
- **PyTorch Build**: `2.14.1+cpu` (`torch.cuda.is_available() == False`)

### 5.2 Training Compute Feasibility
- Training a YOLO11m instance segmentation model (~20M parameters) on ~4,000 images for 50–100 epochs requires:
  - FP16 Tensor Core operations for efficient gradient computation.
  - ~6–8 GB of dedicated GPU VRAM.
- On a CPU, each epoch would require 40–90 minutes. A full training run would take **3 to 5 days** of continuous 100% CPU utilization, causing thermal throttling, desktop unresponsiveness, and high risk of process termination.
- On a Cloud GPU (Google Colab / Kaggle / RunPod with T4 or A100), the exact same training run completes in **60 to 90 minutes**.

---

## 6. Model Training Blueprint (Cloud GPU)

To produce the required checkpoints, training should be executed using the following blueprint on a GPU-enabled cloud platform:

### 6.1 Required Datasets
1. **CarDD (Car Damage Dataset)**:
   - Source: USTC / PIC Lab (`https://cardd-ustc.github.io/`)
   - Size: ~4,000 images with polygon segmentation annotations
   - Target Classes: `dent`, `scratch`, `crack`, `glass_shatter`, `lamp_broken`, `tire_flat`
2. **Carparts-Seg Dataset**:
   - Source: Roboflow Universe / Hugging Face (`yusufnull/car-parts-and-damage-dataset` or `mitbersh/car-parts-segmentation-yolo`)
   - Target Classes: 23 canonical parts matching `CARPARTS_CLASS_MAP`

### 6.2 YOLO11m Segmentation Training Command
```python
from ultralytics import YOLO

# Train CarDD Damage Model
model_damage = YOLO("yolo11m-seg.pt")
model_damage.train(
    data="cardd_segmentation.yaml",
    epochs=60,
    imgsz=640,
    batch=16,
    device=0,
    project="auto_settle_models",
    name="cardd_seg",
)
# Save best.pt -> weights/yolo11m-cardd-seg.pt

# Train Carparts Segmentation Model
model_parts = YOLO("yolo11m-seg.pt")
model_parts.train(
    data="carparts_segmentation.yaml",
    epochs=60,
    imgsz=640,
    batch=16,
    device=0,
    project="auto_settle_models",
    name="carparts_seg",
)
# Save best.pt -> weights/yolo11m-carparts-seg.pt
```

---

## 7. Verification Summary

| Test Suite | Modules Covered | Total Tests | Status | Execution Time |
| :--- | :--- | :---: | :---: | :---: |
| **Stage 2 Unit & Integration** | `test_polygon_intersection_engine`, `test_zoom_anti_inflation`, `test_part_side_resolver`, `test_catalog_and_ledger_grounder`, `test_som_crop_renderer`, `test_dual_mask_orchestrator`, `test_model_compatibility` | 37 | **PASSED** | 13.24s |
| **Stage 2 CI Invariants** | IoP ceiling, zoom anti-inflation, SQL catalogue hit rate, SoM non-occlusion, latency SLA | 5 | **PASSED** | 1.54s |
| **Stage 0 Fast-Fail Gate** | Policy deduplication, container forensics, visual quality gate | 15 | **PASSED** | 31.64s |
| **Stage 1 Identity & Continuity** | Cut detector, plate OCR ANPR, color grounding, object tracker | 18 | **PASSED** | 16.81s |
| **Overall Verification** | Full hermetic pipeline | **75** | **100% GREEN** | — |

---

## 8. Post-Audit Resolution & Milestone Addendum (2026-10-21)

All open items and bottlenecks identified in this audit have been resolved:

1. **Checkpoints Sourced & Verified Locally**:
   - Vehicle Part Segmentation: `weights/carparts-yolo11n-seg.pt` (23 exterior classes verified).
   - Vehicle Damage Segmentation: `weights/cardd-yolov8s-seg.pt` (6 CarDD damage classes verified).
2. **Local Hardware Environment Upgraded**:
   - Environment migrated to Linux WSL2 running PyTorch 2.6.0+cu124 on a physical **NVIDIA GeForce RTX 4060 Laptop GPU** (8 GB VRAM).
   - Confirmed CUDA device mapping: `device = torch.device('cuda:0')`.
3. **Training Automation Toolchain Built**:
   - Added COCO-to-YOLO polygon dataset preparation utility: `tools/model_training/prepare_dataset.py`.
   - Added memory-optimized training runner: `tools/model_training/train_yolo_seg.py` (supporting FP16 AMP, early stopping, and automatic batch scaling).
   - Added one-click shell and batch runners: `scripts/train_wsl.sh` and `scripts/train_windows.bat`.
   - GPU smoke test passed on RTX 4060 GPU with 0.428 GB peak VRAM.
4. **Intent-Conditioned Stage 2 Architecture**:
   - Implemented dynamic claim intent grounding (`app/domain/claim_intent/`) with local FastEmbed ONNX models.
   - Stage 2 now conditions detection on claimed intent, cleanly quarantining background pre-existing defects (`UNCLAIMED_PREEXISTING_DAMAGE`) and raising `ESC-07_CLAIMED_DAMAGE_NOT_FOUND` on missing claims.
5. **Full Suite Green**: Test suite expanded from 75 to **149 tests (100% passing)**.

