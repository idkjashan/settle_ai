# Low-Level Design (LLD): Dual-Mask Part & Damage Segmentation (Stage 2) — `dual_mask_segmentation`

| Document Control | Details |
| :--- | :--- |
| **Document ID** | `LLD-AUTO-SETTLE-STAGE-2-DUAL-MASK-SEGMENTATION` |
| **Version** | `2.0.0 (Frozen Production Specification — Descriptive Module Layout)` |
| **Parent Architecture** | `auto_settle_ai_architecture_adversarial_plan.md` |
| **System** | Auto-Settle AI: Autonomous Video-to-Cash Claims Adjuster |
| **Module Scope** | Stage 2: Dual-Mask Part & Damage Segmentation (`app/domain/dual_mask_segmentation/`) |
| **Target Runtime Stack** | Python 3.12 (`uv`), FastAPI + Uvicorn (`uvloop`), PyTorch 2.4 + CUDA 12.4 / ONNX Runtime FP16, Ultralytics YOLO11 (`yolo11m-carparts-seg.pt` + `yolo11m-cardd-seg.pt`), `Shapely` 2.0 (GEOS C-Library), OpenCV (`cv2`), NumPy, PostgreSQL 16 (`asyncpg`), Redis 7, MinIO / S3 |
| **Latency & Compute SLA** | **$p_{50} \le 240\text{ ms}$**, **$p_{95} \le 420\text{ ms}$** (Hard SLA Ceiling $\le 500\text{ ms}$), **Hard Timeout $750\text{ ms}$** \| **$\le 960\text{ MB}$ Incremental GPU VRAM** (Total System VRAM $\le 2.5\text{ GB} / 8.0\text{ GB}$) |
| **Upstream Dependency** | Stage 1: Vehicle Identity & Continuity Grounding (`app/domain/vehicle_identity_continuity/`) (`COMPLETE & FROZEN`) |
| **Downstream Consumer** | Stage 3: Set-of-Marks VLM Damage Inspection (`app/domain/vlm_damage_inspection/`) |
| **Guardrail Rule IDs** | **`ESC-03`** (Unrepaired Repeat Claim on Same Part in `unrepaired_claims_ledger` $\rightarrow$ Auto-Reject / Fraud Queue)<br>**`ESC-05`** (Opposite-Side Multi-Hit Damage in Single Claim $\rightarrow$ Escalate as Combined Multi-Incident Claim)<br>**`ESC-06`** (Safety-Critical Part or Structural Hazard [`front_glass`, `wheel`, `tire_flat`, `glass_shatter`] $\rightarrow$ Route to Physical Garage)<br>**`ESC-07`** (Low Segmentation Confidence $< 0.45$ or Zero Grounded Damage-Part Overlaps $\rightarrow$ Route to Human Desk Adjuster) |

---

## 1. Executive Summary & Architectural Traceability

### 1.1 TL;DR (Too Long; Didn't Read)
Stage 2 receives the curated, glare-filtered keyframe portfolio ($8\text{--}30$ native 1080p frames) from Stage 1 (`vehicle_identity_continuity`) and executes two specialized instance segmentation models in batched FP16 GPU memory:
1. **Model A (`Carparts-Seg` — `yolo11m-carparts-seg.pt`):** Segments 22 canonical exterior vehicle body panels and assemblies (filtering out class 18 `object`).
2. **Model B (`Damage-Seg` — `yolo11m-cardd-seg.pt`):** Segments 6 distinct surface and structural damage classes (`dent`, `scratch`, `crack`, `glass_shatter`, `lamp_broken`, `tire_flat`).

Using the C++ GEOS vector engine (`Shapely` 2.0), Stage 2 converts pixel masks into self-healed 2D vector polygons (`poly.buffer(0)`), filters boundary spillover ($\ge 10\%$ overlap or $\ge 2500\text{ px}^2$), merges co-located damages on the same panel via geometric `unary_union` (preventing double-counting when a scratch sits inside a dent), and defeats the **"Camera Zoom Inflation Attack"** by decoupling the **Unclipped Panel Area Measurement Frame** (requiring $15\text{px}$ border clearance) from the **Macro VLM Inspection Frame**. Finally, Stage 2 resolves generic part predictions (`front_door` $\rightarrow$ `front_left_door`) via walkaround trajectory propagation, verifies the part against `oem_parts_catalogue` and `unrepaired_claims_ledger` in PostgreSQL 16, pre-evaluates guardrails `ESC-03`, `ESC-05`, `ESC-06`, and `ESC-07`, and renders non-occluding **Set-of-Marks (SoM)** dilated contour crops for Stage 3 alongside normalized SVG polygon paths for the Next.js 15 frontend.

[Full LLD specifications incorporated as defined in Stage 2 document]
