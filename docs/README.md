# Architecture & Engineering Documentation

This directory contains the formal architectural specifications, Low-Level Design (LLD) documents, adversarial stress-testing reports, and presentation materials for **Auto-Settle AI**.

---

## 1. Executive Presentation & Blueprints

- **[`presentation/Auto_Settle_AI_Executive_Presentation.pptx`](presentation/Auto_Settle_AI_Executive_Presentation.pptx)**: Official executive slide deck covering business ROI, unit economics, computer vision pipeline, actuarial pricing, and fraud-mitigation architecture.
- **[`techstack.pdf`](techstack.pdf)**: Complete visual system blueprint and architecture diagrams.

---

## 2. Low-Level Design (LLD) & Specifications

- **[`LLD_OCCLUSION_ROBUST_DAMAGE_TRACKING.md`](LLD_OCCLUSION_ROBUST_DAMAGE_TRACKING.md)**: Mathematical and algorithmic specification for continuous ByteTrack trajectory maintenance, RoIAlign feature extraction, and Hungarian cosine matching during camera pan and zoom.
- **[`lld/`](lld/)**: Detailed module specifications for each pipeline stage:
  - Stage 0: Dual-Modality Fast-Fail Gate
  - Stage 1: Vehicle Identity & Continuity Grounding
  - Stage 2: Conditioned Dual-Mask Segmentation & Damage Quarantine
  - Stage 3: Set-of-Marks (SoM) VLM Forensic Inspection
  - Stage 4: Deterministic Actuarial Pricing Engine
  - Stage 5: Bounded FSM Negotiation Chatbot
  - Stage 6: Settlement Router & Cryptographic Dossier

---

## 3. Adversarial Analysis & Forensic Reports

- **[`ARCHITECTURAL_DEVILS_ADVOCATE_REPORT.md`](ARCHITECTURAL_DEVILS_ADVOCATE_REPORT.md)**: Independent adversarial review stress-testing edge cases: macro camera zoom inflation, glare false positives, double-dipping fraud, and cut-spliced video spoofing.
- **[`STRESS_TEST_AND_SOLUTION_ARCHITECTURE.md`](STRESS_TEST_AND_SOLUTION_ARCHITECTURE.md)**: Solution architecture resolving edge cases identified during stress testing.
- **[`auto_settle_ai_architecture_adversarial_plan.md`](auto_settle_ai_architecture_adversarial_plan.md)**: Original adversarial implementation plan and guardrail specifications.

---

## 4. Model Training & Readiness Audits

- **[`MODEL_SOURCING_AND_TRAINING_REPORT.md`](MODEL_SOURCING_AND_TRAINING_REPORT.md)**: Technical provenance, dataset sourcing (CarDD, Carparts-Seg, COCO), and training toolchain configuration for NVIDIA RTX 4060 GPU.
- **[`STAGE_2_MODEL_AND_DATASET_READINESS_AUDIT.md`](STAGE_2_MODEL_AND_DATASET_READINESS_AUDIT.md)**: Verification of dual YOLO checkpoint weights, class alignments, and inference latency budgets.
- **[`stage2_annotated_samples/`](stage2_annotated_samples/)**: Curated visual crops demonstrating Stage 2 dual-mask segmentations and Stage 3 Set-of-Marks depth markers.

---

## 5. Evaluation Guides

- **[`ANTIGRAVITY_HARNESS_REPORT.md`](ANTIGRAVITY_HARNESS_REPORT.md)**: Engineering audit report documenting the automated test harness, stage latency benchmarks, and scenario pass rates.
- **[`END_TO_END_EVALUATION_AND_HARNESS_GUIDE.md`](END_TO_END_EVALUATION_AND_HARNESS_GUIDE.md)**: Step-by-step developer guide for running the CLI evaluation runner and interpreting audit trails.

