# Auto-Settle AI — Live Claims Desk Frontend

A production-grade, responsive motor claims workstation for **Auto-Settle AI**, unified with the FastAPI backend and operating on real evaluation passes.

---

## 1. Quick Start

Run the unified application with Uvicorn (FastAPI serves both the backend API and frontend static assets):

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser to:
```
http://127.0.0.1:8000/
```

- **Frontend Root**: `http://127.0.0.1:8000/` (Served via `frontend/index.html`)
- **API Documentation**: `http://127.0.0.1:8000/docs` (Swagger UI)
- **Health Check**: `http://127.0.0.1:8000/health`
- **Video Test Assets**: `http://127.0.0.1:8000/test_assets/videos/simple/`
- **Dual-Mask & SoM Artifacts**: `http://127.0.0.1:8000/docs_assets/` and `http://127.0.0.1:8000/evals/`

---

## 2. Core Architecture & Features

### A. Real-Time System 1 Intent Grounding (NLP)
As claimants type their damage narrative during intake, the client-side NLP grounding engine actively parses claimed parts, damage types, and expected severity in real-time. This bounds YOLO segmentation and establishes the baseline for the Conditioned Damage Quarantine engine.

### B. Conditioned Damage Quarantine Engine
Distinguishes admitted claim defects from pre-existing road wear:
- **Billed Claim Items**: Admitted defects matching claimant intent (e.g., driver-side front door crease).
- **Quarantined Road Wear**: Unclaimed peripheral wear (e.g., rear bumper scuffs, normal stone pecks) quarantined to `UNCLAIMED_PREEXISTING_DAMAGE` without triggering false fraud flags (bypassing multi-panel ESC-05 alarms).

### C. Multi-Modality Evidence Inspection Switcher
The evidence inspection panel in the claim workstation provides three complementary viewing modes:
1. **Walkaround Video**: Streams authentic walkaround test assets (e.g. `car_002.mp4`, `car_001.mp4`, `toyota-corolla...mp4`) with continuous trajectory tracking.
2. **Dual-Mask YOLO**: Inspects Stage 2 intent-conditioned dual-mask segmentations with pixel-level IoP (Intersection over Panel) metrics.
3. **Set-of-Marks (SoM) VLM**: Inspects Stage 3 Qwen2-VL depth markers and pre-existing rust detection crops.

### D. Dark Mode & Visual Polish
- Supports light and dark modes with persistent local preference storage (`settleai_theme`).
- Automatically syncs with system `prefers-color-scheme`.
- Built according to Apple Human Interface Guidelines and editorial design principles (restrained color palettes, mineral surfaces, clear typography).

### E. Persistent Claim History
All claims, customer negotiation turns, severity grade adjustments, and UPI voucher disbursements persist to browser `localStorage` (`settleai_claims_history_v2`). Reloading or returning to the claims desk retains full portfolio state.

### F. Bounded FSM Negotiation & UPI Voucher Disbursement
- Concession curves are mathematically bounded between 75% (opening) and 95% (cap) of the eligible repair cost.
- Hard guardrail ceiling blocks automated payouts above ₹25,000 (Rule ESC-08).
- Simulated instant UPI disbursement transfers funds upon claimant acceptance and commits the record to the cryptographic ledger.

---

## 3. Benchmark Evaluation Cohorts

The workstation is pre-seeded with authentic benchmark scenarios from the evaluation suite:

| Claim ID | Vehicle | Evidence Asset | Finding | Outcome |
| :--- | :--- | :--- | :--- | :--- |
| **CLM-48291** | Hyundai Creta 2022 | `car_002.mp4` | L4 Creased door dent | Ready to settle (₹7,500 – ₹9,500) |
| **CLM-48290** | Maruti Baleno 2021 | `car_001.mp4` | L1 Bumper surface scuff | Ready to settle (₹2,050 – ₹2,600) |
| **CLM-48288** | Toyota Corolla 2020 | `toyota-corolla...mp4` | Deep flank dent + rust | Escalated: ESC-04 (Pre-existing wear) |
| **CLM-48287** | Tata Nexon 2023 | `car_004.mp4` | L2 Bumper scratch | Settled: ₹4,590 disbursed via UPI |
| **CLM-48284** | Kia Seltos 2023 | `car_005.mp4` | L5 Windshield crack | Escalated: ESC-06 (Safety critical) |

---

## 4. Verification & Testing

Run full headless browser verification with Playwright:

```bash
# Verify all workstation routes, dark mode, NLP intent, and media switching
python -m pytest tests/
```
