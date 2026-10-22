"""
evals/comprehensive_harness.py
Master End-to-End Evaluation & Testing Harness for Auto-Settle AI.

Executes claims across all 7 pipeline stages:
  Stage 0: Dual-Modality Fast-Fail Gate (Container Forensics, NLE Check, Visual Quality)
  System 1: Dynamic Claim Intent Grounding (FastEmbed ONNX & Dynamic Taxonomy)
  Stage 1: Vehicle Identity & Continuity Grounding (CutDetector, Plate OCR, Color Grounding, ByteTrack)
  Stage 2: Conditioned Dual-Mask Segmentation & Damage Quarantine (Dual YOLO, Shapely IoP, OEM Catalogue)
  Stage 3: Set-of-Marks VLM Damage Inspection & Depth Grading (SoM Crops, L1-L5 Depth, Rust/Misalignment Gating)
  Stage 4: Deterministic Actuarial Pricing Engine (Depreciation, Labor, Paint Overlap, GST, Deductible, NCB Advisory)
  Stage 5: Negotiation Chatbot FSM (Cryptographic HMAC-SHA256 Signed Offer Cards, Multi-Turn Counteroffers)
  Stage 6: Settlement & Escalation (Penny-Balanced Apportionment, Instant UPI Voucher, Surveyor Dossier, PDF Generation)

Features:
  - Supports ANY video file format (or structured photo pack).
  - Flexible Stage Bypassing: Allows skipping any stage (e.g., skip Stage 0, bypass Stage 1 cuts to test Stage 2/3).
  - Automatic OpenCV Keyframe Sampler: When Stage 1 is bypassed or video has cuts, extracts real keyframes for Stage 2.
  - Complete Granular Audit Trail: Per-stage status, latency, inputs, outputs, decisions, escalation codes, and artifacts.
  - Real-time Event Streaming: Emits progress callbacks matching the frontend SSE protocol.
  - Interactive & Automated Modes: Seamlessly operable via CLI, Web Testbench, Python API, or CI test runners.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple, Union
import uuid

import cv2
import numpy as np

# Ensure root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import logger
from app.infrastructure.db.models import Claim, InsuredPolicy, OemPart, UnrepairedClaim
from app.infrastructure.db.repositories import (
    ClaimRepository,
    DemoResetRepository,
    OemRepository,
    PolicyRepository,
    UnrepairedClaimsRepository,
)
from app.infrastructure.cache.redis_manager import RedisManager, redis_manager
from tests.in_memory_db import (
    FakeAsyncSession,
    in_memory_db,
    patch_in_memory_db,
)

# Patch in-memory DB and Redis mocks so eval harness can run completely standalone & hermetically
patch_in_memory_db()


# ==============================================================================
# AUDIT TRAIL DATA STRUCTURES
# ==============================================================================

@dataclass
class StageAuditDTO:
    """Detailed audit information for an individual pipeline stage."""
    stage_name: str
    status: str  # "PASSED", "FAILED", "ESCALATED", "BYPASSED", "SKIPPED"
    latency_ms: float
    started_at: str
    completed_at: str
    escalation_code: Optional[str] = None
    failure_codes: List[str] = field(default_factory=list)
    summary_message: str = ""
    inputs_summary: Dict[str, Any] = field(default_factory=dict)
    outputs_summary: Dict[str, Any] = field(default_factory=dict)
    decision_reasoning: str = ""
    artifacts: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuditTrail:
    """Master structured audit trail for an entire claim evaluation run."""
    claim_id: str
    policy_id: str
    media_path: Union[str, List[str]]
    modality: str  # "video" or "photo_pack"
    claim_description: str
    bypassed_stages: List[str]
    overrides_applied: Dict[str, Any]
    started_at: str
    completed_at: str
    total_execution_ms: float
    final_verdict: str  # e.g. "SETTLED_CASH", "ESCALATED_HUMAN", "REJECTED_STAGE0", "REJECTED_STAGE1"
    escalation_code: Optional[str] = None
    stage_audits: Dict[str, StageAuditDTO] = field(default_factory=dict)
    financial_summary: Optional[Dict[str, Any]] = None
    negotiation_summary: Optional[Dict[str, Any]] = None
    perception_summary: Optional[Dict[str, Any]] = None
    damage_report: List[Dict[str, Any]] = field(default_factory=list)
    generated_artifacts: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["stage_audits"] = {k: v.to_dict() if hasattr(v, "to_dict") else v for k, v in self.stage_audits.items()}
        return d

    def to_json(self, indent: int = 2) -> str:
        def _default_serializer(obj):
            if isinstance(obj, Decimal):
                return str(obj)
            if isinstance(obj, Path):
                return str(obj)
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if isinstance(obj, uuid.UUID):
                return str(obj)
            return str(obj)
        return json.dumps(self.to_dict(), indent=indent, default=_default_serializer)


# ==============================================================================
# KEYFRAME EXTRACTION UTILITY (FOR BYPASSED STAGE 1 OR CUT VIDEOS)
# ==============================================================================

def extract_uniform_keyframes_from_video(
    video_path: Union[str, Path],
    output_dir: Union[str, Path],
    target_count: int = 8,
) -> Dict[str, str]:
    """
    Extracts evenly spaced high-quality keyframes from any video using OpenCV.
    Ensures Stage 2 dual-YOLO segmentation can run even if Stage 1 is bypassed
    or video contains scene cuts/splices.
    """
    v_path = Path(video_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not v_path.exists():
        raise FileNotFoundError(f"Video file not found at: {v_path}")

    cap = cv2.VideoCapture(str(v_path))
    if not cap.isOpened():
        raise ValueError(f"OpenCV failed to open video: {v_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        total_frames = 300  # Fallback estimate

    # Generate frame indices distributed across duration (skipping 5% intro and outro)
    step = max(1, int(total_frames / (target_count + 1)))
    frame_indices = [int(step * (i + 1)) for i in range(target_count)]
    frame_indices = [min(f, total_frames - 1) for f in frame_indices]

    keyframes_map: Dict[str, str] = {}
    current_idx = 0
    saved_count = 0

    while cap.isOpened() and saved_count < target_count:
        ret, frame = cap.read()
        if not ret:
            break

        if current_idx in frame_indices:
            saved_count += 1
            kf_name = f"keyframe_{saved_count:02d}"
            kf_path = out_dir / f"{kf_name}.jpg"
            cv2.imwrite(str(kf_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            keyframes_map[kf_name] = str(kf_path)

        current_idx += 1

    cap.release()

    # Fallback if video was extremely short
    if not keyframes_map and current_idx > 0:
        cap = cv2.VideoCapture(str(v_path))
        ret, frame = cap.read()
        if ret:
            kf_path = out_dir / "keyframe_01.jpg"
            cv2.imwrite(str(kf_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            keyframes_map["keyframe_01"] = str(kf_path)
        cap.release()

    return keyframes_map


# ==============================================================================
# DEFAULT POLICY SEEDER
# ==============================================================================

def ensure_test_policies():
    """Ensure standard test policies exist in in-memory database."""
    extra_policies = {
        "POL-HAPPY-001": InsuredPolicy(
            policy_id="POL-HAPPY-001",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="MH12DE1433",
            vin_last_6="99112A",
            make="Hyundai",
            model="Creta",
            manufacturing_year=2023,
            registered_color="WHITE",
            registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 45, "v_min": 180, "v_max": 255},
            paint_type="solid",
            zero_dep_addon=True,
            compulsory_deductible_inr=Decimal("1000.00"),
            estimated_ncb_loss_inr=Decimal("3200.00"),
        ),
        "POL-SUBARU-002": InsuredPolicy(
            policy_id="POL-SUBARU-002",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="MH12DE1433",
            vin_last_6="11223A",
            make="Subaru",
            model="Impreza",
            manufacturing_year=2022,
            registered_color="BLUE",
            registered_color_hsv={"h_min": 100, "h_max": 130, "s_min": 80, "s_max": 255, "v_min": 50, "v_max": 255},
            paint_type="metallic",
            zero_dep_addon=True,
            compulsory_deductible_inr=Decimal("1000.00"),
            estimated_ncb_loss_inr=Decimal("3000.00"),
        ),
        "POL-HILUX-010": InsuredPolicy(
            policy_id="POL-HILUX-010",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="1ILJ681",
            vin_last_6="77112A",
            make="Toyota",
            model="Hilux",
            manufacturing_year=2021,
            registered_color="WHITE",
            registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 45, "v_min": 180, "v_max": 255},
            paint_type="solid",
            zero_dep_addon=True,
            compulsory_deductible_inr=Decimal("1000.00"),
            estimated_ncb_loss_inr=Decimal("3000.00"),
        ),
        "POL-FIAT-011": InsuredPolicy(
            policy_id="POL-FIAT-011",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="AX72JJV",
            vin_last_6="88223B",
            make="Fiat",
            model="500",
            manufacturing_year=2023,
            registered_color="BLUE",
            registered_color_hsv={"h_min": 95, "h_max": 135, "s_min": 40, "s_max": 255, "v_min": 40, "v_max": 255},
            paint_type="metallic",
            zero_dep_addon=True,
            compulsory_deductible_inr=Decimal("1000.00"),
            estimated_ncb_loss_inr=Decimal("2500.00"),
        ),
        "POL-GOLF-012": InsuredPolicy(
            policy_id="POL-GOLF-012",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="GD73KZS",
            vin_last_6="99334C",
            make="Volkswagen",
            model="Golf",
            manufacturing_year=2024,
            registered_color="GREY",
            registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 50, "v_min": 40, "v_max": 160},
            paint_type="metallic",
            zero_dep_addon=True,
            compulsory_deductible_inr=Decimal("1000.00"),
            estimated_ncb_loss_inr=Decimal("3500.00"),
        ),
        "POL-COROLLA-013": InsuredPolicy(
            policy_id="POL-COROLLA-013",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="TX98K5512",
            vin_last_6="77112C",
            make="Toyota",
            model="Corolla",
            manufacturing_year=2021,
            registered_color="SILVER",
            registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 40, "v_min": 140, "v_max": 255},
            paint_type="metallic",
            zero_dep_addon=True,
            compulsory_deductible_inr=Decimal("1000.00"),
            estimated_ncb_loss_inr=Decimal("3500.00"),
        ),
    }
    for pid, pol in extra_policies.items():
        if pid not in in_memory_db.policies:
            in_memory_db.policies[pid] = pol


# ==============================================================================
# COMPREHENSIVE EVALUATION HARNESS CLASS
# ==============================================================================

class ComprehensiveEvaluationHarness:
    """
    Unified end-to-end evaluation & testing harness orchestrating all 7 stages
    with stage bypassing, live audit trails, and frontend-like testing.
    """

    def __init__(
        self,
        output_artifacts_dir: Union[str, Path] = Path("evals/artifacts"),
        vlm_provider: str = "mock",
        db_session: Optional[FakeAsyncSession] = None,
        redis_client: Optional[Any] = None,
    ):
        ensure_test_policies()
        self.artifacts_dir = Path(output_artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.vlm_provider = vlm_provider
        self.db = db_session or FakeAsyncSession()
        self.redis = redis_client or redis_manager

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def evaluate(
        self,
        media_path: Union[str, Path, List[Union[str, Path]]],
        claim_description: str = "Scratched front bumper and dented front right door",
        policy_id: str = "POL-HAPPY-001",
        claim_id: Optional[uuid.UUID] = None,
        bypass_stages: Optional[Union[List[str], Set[str]]] = None,
        overrides: Optional[Dict[str, Any]] = None,
        event_callback: Optional[Callable[[str, Dict[str, Any]], Coroutine[Any, Any, None]]] = None,
        negotiation_strategy: str = "counter_then_accept",  # "immediate_accept", "counter_then_accept", "reject_to_surveyor", "interactive"
        interactive_negotiation_handler: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]]] = None,
        beneficiary_upi: str = "claimant@upi",
    ) -> AuditTrail:
        """
        Executes end-to-end claims evaluation across all stages.
        """
        claim_uuid = claim_id or uuid.uuid4()
        started_at = self._now_iso()
        t_global_start = time.perf_counter()

        bypass_set = set(s.lower().strip() for s in (bypass_stages or []))
        opts = overrides or {}

        # Resolve modality: video vs photo pack
        is_photo_pack = isinstance(media_path, list)
        modality = "photo_pack" if is_photo_pack else "video"

        # Setup audit trail container
        audit = AuditTrail(
            claim_id=str(claim_uuid),
            policy_id=policy_id,
            media_path=[str(p) for p in media_path] if is_photo_pack else str(media_path),
            modality=modality,
            claim_description=claim_description,
            bypassed_stages=list(bypass_set),
            overrides_applied=opts,
            started_at=started_at,
            completed_at="",
            total_execution_ms=0.0,
            final_verdict="IN_PROGRESS",
        )

        async def _notify(stage_name: str, status: str, payload: Dict[str, Any]):
            if event_callback:
                try:
                    await event_callback(f"{stage_name}_{status}", payload)
                except Exception as cb_err:
                    logger.warning(f"Event callback exception: {cb_err}")

        # Ensure claim record exists in in-memory DB
        policy_repo = PolicyRepository(self.db)
        claim_repo = ClaimRepository(self.db)
        db_policy = await policy_repo.get_by_id(policy_id)
        if not db_policy:
            # Fallback to POL-HAPPY-001 if unknown
            policy_id = "POL-HAPPY-001"
            db_policy = await policy_repo.get_by_id(policy_id)

        # Ensure claim record is created in in-memory DB
        in_memory_db.claims[claim_uuid] = Claim(
            claim_id=claim_uuid,
            policy_id=policy_id,
            video_sha256=f"sha_{claim_uuid}",
            current_stage="STAGE_0_SANITY",
            claim_status="IN_PROGRESS",
            is_demo_rehearsal=True,
            created_at=datetime.now(),
        )

        claim_scratch_dir = self.artifacts_dir / str(claim_uuid)
        claim_scratch_dir.mkdir(parents=True, exist_ok=True)
        extracted_keyframes: Dict[str, str] = {}

        # ----------------------------------------------------------------------
        # PERCEPTION: Occlusion-Robust Re-ID Damage Tracking (C4 RoIAlign + Temporal Confirmation)
        # ----------------------------------------------------------------------
        enable_tracking = opts.get("enable_tracking", True)
        if modality == "video" and enable_tracking and "perception_tracking" not in bypass_set and not opts.get("bypass_tracking", False):
            t0_trk = time.perf_counter()
            trk_start = self._now_iso()
            trk_audit = StageAuditDTO(
                stage_name="PERCEPTION_OCCLUSION_REID_TRACKING",
                status="PENDING",
                latency_ms=0.0,
                started_at=trk_start,
                completed_at="",
            )
            try:
                from app.domain.perception.tracking.occlusion_reid_tracker import OcclusionReIDTracker
                cardd_w = "weights/cardd-yolov8s-seg.pt"
                tracker = OcclusionReIDTracker(
                    weights_path=cardd_w if Path(cardd_w).exists() else None,
                    conf_threshold=opts.get("tracking_conf", 0.18),
                )
                stride = opts.get("tracking_stride", 3)
                tracking_result = tracker.track_video(
                    video_path=media_path,
                    conf=opts.get("tracking_conf", 0.18),
                    vid_stride=stride,
                )
                trk_audit.status = "PASSED"
                trk_audit.decision_reasoning = (
                    f"OcclusionReIDTracker processed {tracking_result.total_frames} frames: "
                    f"reduced {tracking_result.raw_unique_ids_count} raw ByteTrack IDs to "
                    f"{tracking_result.confirmed_unique_ids_count} persistent damage tracks "
                    f"({tracking_result.id_switch_reduction_pct}% ID switch reduction)."
                )
                trk_audit.outputs_summary = {
                    "total_frames_processed": tracking_result.total_frames,
                    "raw_unique_ids": tracking_result.raw_unique_ids_count,
                    "reid_unique_ids": tracking_result.reid_unique_ids_count,
                    "confirmed_unique_ids": tracking_result.confirmed_unique_ids_count,
                    "id_switch_reduction_pct": tracking_result.id_switch_reduction_pct,
                    "confirmed_damage_classes": [t.class_name for t in tracking_result.confirmed_tracks],
                }
                audit.perception_summary = trk_audit.outputs_summary

                # Save annotated tracking visualizations & seed candidate keyframes
                annot_dir = claim_scratch_dir / "annotated_frames"
                annot_dir.mkdir(parents=True, exist_ok=True)
                tracked_artifact_paths: List[str] = []

                for t_sum in tracking_result.confirmed_tracks:
                    if t_sum.best_frame_img is not None:
                        kf_key = f"track_{t_sum.final_id}_{t_sum.class_name}"
                        kf_p = claim_scratch_dir / "keyframes" / f"{kf_key}.jpg"
                        kf_p.parent.mkdir(parents=True, exist_ok=True)
                        cv2.imwrite(str(kf_p), t_sum.best_frame_img)
                        extracted_keyframes[kf_key] = str(kf_p)

                        vis_frame = t_sum.best_frame_img.copy()
                        bx1, by1, bx2, by2 = t_sum.best_bbox_xyxy
                        cv2.rectangle(vis_frame, (bx1, by1), (bx2, by2), (0, 255, 0), 2)
                        lbl = f"TRACK #{t_sum.final_id}: {t_sum.class_name.upper()} ({t_sum.best_confidence:.2f})"
                        cv2.putText(vis_frame, lbl, (bx1, max(25, by1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                        trk_vis_path = annot_dir / f"tracked_damage_tr{t_sum.final_id}_{t_sum.class_name}.jpg"
                        cv2.imwrite(str(trk_vis_path), vis_frame)
                        tracked_artifact_paths.append(str(trk_vis_path))

                audit.generated_artifacts["tracked_damage_images"] = tracked_artifact_paths
                trk_audit.artifacts["tracked_images"] = tracked_artifact_paths
                await _notify("PERCEPTION", "TRACKED", trk_audit.outputs_summary)

            except Exception as trk_err:
                trk_audit.status = "WARNING"
                trk_audit.summary_message = f"Perception tracking fallback: {trk_err}"
                logger.warning(f"OcclusionReIDTracker error: {trk_err}")

            trk_audit.latency_ms = round((time.perf_counter() - t0_trk) * 1000.0, 2)
            trk_audit.completed_at = self._now_iso()
            audit.stage_audits["perception_tracking"] = trk_audit

        # ----------------------------------------------------------------------
        # STAGE 0: Dual-Modality Fast-Fail Gate
        # ----------------------------------------------------------------------
        t0_s0 = time.perf_counter()
        s0_start = self._now_iso()
        s0_audit = StageAuditDTO(
            stage_name="STAGE_0_FAST_FAIL_GATE",
            status="PENDING",
            latency_ms=0.0,
            started_at=s0_start,
            completed_at="",
        )

        s0_passed = False
        s0_failure_codes = []
        c_rep_details = {}

        if "stage_0" in bypass_set or opts.get("bypass_stage_0", False):
            s0_passed = True
            s0_audit.status = "BYPASSED"
            s0_audit.decision_reasoning = "Stage 0 explicitly bypassed by evaluation runner configuration."
            s0_audit.outputs_summary = {"passed": True, "bypassed": True}
            await _notify("STAGE_0", "BYPASSED", {"claim_id": str(claim_uuid)})
        else:
            try:
                from app.domain.fast_fail_gate.container_forensics import (
                    container_forensics_validator,
                    validate_photo_pack,
                )
                from app.domain.fast_fail_gate.visual_quality_gate import (
                    visual_quality_validator,
                    validate_photos,
                )

                if modality == "video":
                    v_p = Path(media_path)
                    if not v_p.exists():
                        s0_failure_codes.append(f"FILE_NOT_FOUND: {media_path}")
                    else:
                        file_sz = v_p.stat().st_size
                        c_rep = container_forensics_validator.validate(v_p, f"sha_{claim_uuid}", file_sz)
                        v_rep = visual_quality_validator.validate(v_p, c_rep)
                        s0_passed = c_rep.passed and v_rep.passed
                        s0_failure_codes = list(set((c_rep.failure_codes or []) + (v_rep.failure_codes or [])))
                        c_rep_details = {
                            "width": c_rep.width,
                            "height": c_rep.height,
                            "fps": c_rep.effective_fps,
                            "duration_sec": c_rep.duration_sec,
                            "mean_luminance": getattr(v_rep, "mean_luminance_aggregate", None),
                            "mean_sharpness": getattr(v_rep, "mean_sharpness_aggregate", None),
                        }
                else:
                    photo_paths = [Path(p) for p in media_path]
                    p_rep = validate_photo_pack(photo_paths)
                    v_rep = validate_photos(photo_paths)
                    s0_passed = p_rep.passed and v_rep.passed
                    s0_failure_codes = list(set((p_rep.failure_codes or []) + (v_rep.failure_codes or [])))
                    c_rep_details = {
                        "photo_count": p_rep.photo_count,
                        "resolutions": [str(r) for r in getattr(p_rep, "resolutions", [])],
                        "mean_sharpness": getattr(v_rep, "mean_sharpness_aggregate", None),
                    }

                s0_audit.status = "PASSED" if s0_passed else "FAILED"
                s0_audit.failure_codes = s0_failure_codes
                s0_audit.outputs_summary = {"passed": s0_passed, "details": c_rep_details}
                s0_audit.decision_reasoning = (
                    "Sanity and visual quality gates passed."
                    if s0_passed
                    else f"Sanity gate failed with codes: {s0_failure_codes}"
                )
                await _notify("STAGE_0", s0_audit.status, {"claim_id": str(claim_uuid), "passed": s0_passed})

            except Exception as s0_err:
                s0_audit.status = "FAILED"
                s0_audit.failure_codes.append(f"EXCEPTION: {str(s0_err)}")
                s0_audit.summary_message = str(s0_err)

        s0_audit.latency_ms = round((time.perf_counter() - t0_s0) * 1000.0, 2)
        s0_audit.completed_at = self._now_iso()
        audit.stage_audits["stage_0"] = s0_audit

        if not s0_passed and not opts.get("force_continue", False):
            audit.final_verdict = "REJECTED_STAGE0"
            audit.escalation_code = "ESC-00"
            audit.total_execution_ms = round((time.perf_counter() - t_global_start) * 1000.0, 2)
            audit.completed_at = self._now_iso()
            return audit

        # ----------------------------------------------------------------------
        # SYSTEM 1: Dynamic Claim Intent Grounding
        # ----------------------------------------------------------------------
        t0_intent = time.perf_counter()
        intent_start = self._now_iso()
        intent_audit = StageAuditDTO(
            stage_name="SYSTEM_1_INTENT_GROUNDING",
            status="PENDING",
            latency_ms=0.0,
            started_at=intent_start,
            completed_at="",
            inputs_summary={"claim_description": claim_description},
        )

        claim_intent = None
        if "intent_grounding" in bypass_set or opts.get("bypass_intent", False):
            intent_audit.status = "BYPASSED"
            intent_audit.decision_reasoning = "System 1 Intent Grounding bypassed."
        elif claim_description and claim_description.strip():
            try:
                from app.domain.claim_intent.intent_grounder import get_claim_intent_grounder
                grounder = get_claim_intent_grounder()
                claim_intent = grounder.ground(claim_description)
                intent_audit.status = "PASSED"
                intent_audit.outputs_summary = {
                    "claimed_parts": claim_intent.claimed_parts,
                    "claimed_damages": claim_intent.claimed_damages,
                    "is_empty": getattr(claim_intent, "is_empty", False),
                }
                intent_audit.decision_reasoning = (
                    f"Extracted {len(claim_intent.claimed_parts)} parts: {claim_intent.claimed_parts} "
                    f"and damages: {claim_intent.claimed_damages}"
                )
                await _notify("INTENT", "GROUNDED", intent_audit.outputs_summary)
            except Exception as intent_err:
                intent_audit.status = "FAILED"
                intent_audit.summary_message = f"Intent extraction failure: {intent_err}"

        intent_audit.latency_ms = round((time.perf_counter() - t0_intent) * 1000.0, 2)
        intent_audit.completed_at = self._now_iso()
        audit.stage_audits["system_1_intent"] = intent_audit

        # ----------------------------------------------------------------------
        # STAGE 1: Vehicle Identity & Continuity Grounding
        # ----------------------------------------------------------------------
        t0_s1 = time.perf_counter()
        s1_start = self._now_iso()
        s1_audit = StageAuditDTO(
            stage_name="STAGE_1_IDENTITY_CONTINUITY",
            status="PENDING",
            latency_ms=0.0,
            started_at=s1_start,
            completed_at="",
        )

        stage1_passed = False
        telemetry = None

        bypass_stage1 = "stage_1" in bypass_set or opts.get("bypass_stage_1", False)
        ignore_cuts = opts.get("ignore_cuts", False)

        if bypass_stage1:
            # Stage 1 explicitly bypassed: extract candidate keyframes via OpenCV
            s1_audit.status = "BYPASSED"
            s1_audit.decision_reasoning = "Stage 1 bypassed. Extracting uniform candidate keyframes via OpenCV for Stage 2."
            if modality == "video":
                extracted_keyframes = extract_uniform_keyframes_from_video(
                    video_path=media_path,
                    output_dir=claim_scratch_dir / "keyframes",
                    target_count=opts.get("keyframe_count", 8),
                )
            else:
                photo_paths = [Path(p) for p in media_path]
                for idx, pp in enumerate(photo_paths, 1):
                    extracted_keyframes[f"photo_{idx:02d}"] = str(pp)

            s1_audit.outputs_summary = {
                "bypassed": True,
                "keyframes_extracted": len(extracted_keyframes),
                "keyframe_keys": list(extracted_keyframes.keys()),
            }
            stage1_passed = True
            await _notify("STAGE_1", "BYPASSED", s1_audit.outputs_summary)

        else:
            try:
                from app.domain.vehicle_identity_continuity.orchestrator import (
                    VehicleIdentityContinuityOrchestrator,
                )
                from app.domain.vehicle_identity_continuity.cut_detector import cut_detector
                from app.domain.vehicle_identity_continuity.plate_ocr_validator import plate_ocr_validator
                from app.domain.vehicle_identity_continuity.color_grounding_validator import color_grounding_validator
                from app.domain.vehicle_identity_continuity.object_tracker import object_tracker

                stage1_orch = VehicleIdentityContinuityOrchestrator(
                    policy_repo=policy_repo,
                    claim_repo=claim_repo,
                    redis_mgr=self.redis,
                    cut_det=cut_detector,
                    plate_val=plate_ocr_validator,
                    color_val=color_grounding_validator,
                    tracker=object_tracker,
                )

                if modality == "video":
                    v_p = Path(media_path)
                    # If ignore_cuts is set, override cut detector on this run
                    if ignore_cuts:
                        from app.domain.vehicle_identity_continuity.schemas import CutDetectionResult
                        original_cut_eval = cut_detector.evaluate
                        cut_detector.evaluate = lambda *args, **kwargs: CutDetectionResult(is_continuous=True, evaluated_frames=100)

                    try:
                        telemetry = await stage1_orch.execute(
                            claim_id=claim_uuid,
                            scratch_video_path=v_p,
                            policy_id=policy_id,
                            is_demo_rehearsal=True,
                        )
                    finally:
                        if ignore_cuts:
                            cut_detector.evaluate = original_cut_eval
                else:
                    photo_paths = [Path(p) for p in media_path]
                    telemetry = await stage1_orch.execute_photo_pack(
                        claim_id=claim_uuid,
                        photo_paths=photo_paths,
                        policy_id=policy_id,
                        is_demo_rehearsal=True,
                    )

                stage1_passed = bool(telemetry and telemetry.passed)
                s1_audit.status = "PASSED" if stage1_passed else "ESCALATED"
                s1_audit.escalation_code = getattr(telemetry, "escalation_code", None)
                s1_audit.failure_codes = []
                if telemetry and telemetry.tracking_report:
                    for k, v in telemetry.tracking_report.saved_keyframes.items():
                        extracted_keyframes[k] = str(v)
                    for i, p_str in enumerate(getattr(telemetry.tracking_report, "curated_keyframes", []) or [], 1):
                        extracted_keyframes.setdefault(f"keyframe_{i:02d}", str(p_str))

                s1_audit.outputs_summary = {
                    "passed": stage1_passed,
                    "plate_extracted": getattr(getattr(telemetry, "plate_report", None), "extracted_plate", None),
                    "color_matched": getattr(getattr(telemetry, "color_report", None), "is_color_match", None),
                    "keyframes_count": len(extracted_keyframes),
                }
                s1_audit.decision_reasoning = (
                    "Vehicle continuity, plate ANPR, and paint color verified."
                    if stage1_passed
                    else f"Stage 1 escalated with code: {s1_audit.escalation_code}"
                )
                await _notify("STAGE_1", s1_audit.status, s1_audit.outputs_summary)

            except Exception as s1_err:
                s1_audit.status = "FAILED"
                s1_audit.failure_codes.append(f"STAGE1_EXCEPTION: {str(s1_err)}")
                s1_audit.summary_message = str(s1_err)

        s1_audit.latency_ms = round((time.perf_counter() - t0_s1) * 1000.0, 2)
        s1_audit.completed_at = self._now_iso()
        s1_audit.artifacts["keyframes"] = extracted_keyframes
        audit.stage_audits["stage_1"] = s1_audit

        # If Stage 1 failed and user did not force continue:
        if not stage1_passed and not opts.get("force_continue", False):
            audit.final_verdict = f"ESCALATED_{s1_audit.escalation_code or 'STAGE1'}"
            audit.escalation_code = s1_audit.escalation_code or "ESC-02"
            audit.total_execution_ms = round((time.perf_counter() - t_global_start) * 1000.0, 2)
            audit.completed_at = self._now_iso()
            return audit

        # If keyframes were not extracted (e.g. cut failure with force_continue), sample now
        if not extracted_keyframes:
            if modality == "video":
                extracted_keyframes = extract_uniform_keyframes_from_video(
                    video_path=media_path,
                    output_dir=claim_scratch_dir / "keyframes",
                    target_count=opts.get("keyframe_count", 8),
                )
            else:
                for idx, pp in enumerate(media_path, 1):
                    extracted_keyframes[f"photo_{idx:02d}"] = str(pp)
            s1_audit.artifacts["keyframes"] = extracted_keyframes

        # ----------------------------------------------------------------------
        # STAGE 2: Conditioned Dual-Mask Segmentation & Damage Quarantine
        # ----------------------------------------------------------------------
        t0_s2 = time.perf_counter()
        s2_start = self._now_iso()
        s2_audit = StageAuditDTO(
            stage_name="STAGE_2_DUAL_MASK_SEGMENTATION",
            status="PENDING",
            latency_ms=0.0,
            started_at=s2_start,
            completed_at="",
            inputs_summary={"keyframe_count": len(extracted_keyframes)},
        )

        stage3_payload = None
        bypass_stage2 = "stage_2" in bypass_set or opts.get("bypass_stage_2", False)

        if bypass_stage2:
            s2_audit.status = "BYPASSED"
            s2_audit.decision_reasoning = "Stage 2 bypassed by user."
            # Construct synthetic Stage 3 handoff payload if available or mocked
            from app.domain.dual_mask_segmentation.schemas import (
                Stage3HandoffPayload,
                GroundedDamagedPart,
                SVGOverlayPayload,
                OEMPartCatalogueRecord,
            )
            cat_rec = OEMPartCatalogueRecord(
                canonical_part_key="front_bumper",
                display_part_name="Front Bumper Cover",
                oem_part_number="86511-M0000",
                part_material="plastic",
                depreciation_rate_non_zero_dep=0.50,
                oem_part_cost_inr=8800.0,
                rr_labour_inr=850.0,
                denting_base_labour_inr=1100.0,
                full_panel_paint_inr=3800.0,
                pdr_or_polish_flat_inr=800.0,
                is_repairable=True,
                is_safety_critical=False,
            )
            svg_rec = SVGOverlayPayload(
                keyframe_key="keyframe_01",
                view_box="0 0 1920 1080",
                part_svg_points_norm=[(0.1, 0.1), (0.9, 0.1), (0.9, 0.5), (0.1, 0.5)],
                damage_svg_points_norm=[(0.4, 0.2), (0.6, 0.2), (0.6, 0.3), (0.4, 0.3)],
            )
            grounded_dummy = [
                GroundedDamagedPart(
                    canonical_part_key="front_bumper",
                    raw_detected_part_classes=["front_bumper"],
                    side_resolution_method="ANPR_ANCHOR",
                    display_part_name="Front Bumper Cover",
                    oem_part_number="86511-M0000",
                    part_material="plastic",
                    is_repairable=True,
                    is_safety_critical=False,
                    detected_damage_classes=["scratch"],
                    primary_damage_class="scratch",
                    final_iop_ratio=0.08,
                    iop_percentage=8.0,
                    iop_estimation_method="UNCLIPPED_GEOS",
                    zoom_clipped_frames_filtered=0,
                    persistence_frame_count=3,
                    part_confidence=0.88,
                    damage_confidence=0.82,
                    area_measurement_keyframe="keyframe_01",
                    vlm_closeup_keyframe="keyframe_01",
                    som_annotated_crop_path=claim_scratch_dir / "front_bumper_som.jpg",
                    som_raw_crop_path=claim_scratch_dir / "front_bumper_raw.jpg",
                    svg_overlay=svg_rec,
                    catalogue_record=cat_rec,
                    is_claimed=True,
                )
            ]
            stage3_payload = Stage3HandoffPayload(
                claim_id=claim_uuid,
                policy_id=policy_id,
                registration_number=getattr(db_policy, "registration_number", "MH12DE1433"),
                make=getattr(db_policy, "make", "Hyundai"),
                model=getattr(db_policy, "model", "Creta"),
                grounded_parts=grounded_dummy,
                telemetry={},
                claim_intent=claim_intent,
            )
            s2_audit.outputs_summary = {"grounded_parts_count": 1, "bypassed": True}
            await _notify("STAGE_2", "BYPASSED", s2_audit.outputs_summary)

        else:
            try:
                from app.domain.vehicle_identity_continuity.schemas import Stage2HandoffPayload
                from app.domain.dual_mask_segmentation.config import Stage2Settings
                from app.domain.dual_mask_segmentation.orchestrator import get_stage2_orchestrator
                from app.domain.dual_mask_segmentation.exceptions import (
                    Stage2Error,
                    Stage2ClaimedDamageNotFoundError,
                    Stage2ModelCompatibilityError,
                )

                ref_path = str(media_path[0]) if is_photo_pack else str(media_path)
                s2_payload = Stage2HandoffPayload(
                    claim_id=claim_uuid,
                    policy_id=policy_id,
                    scratch_video_path=ref_path,
                    keyframe_paths=extracted_keyframes,
                    vehicle_telemetry=telemetry,
                    claim_intent=claim_intent,
                )

                # Resolve valid weights
                cp_weights = "weights/carparts-yolo11n-seg.pt"
                cd_weights = "weights/cardd-yolov8s-seg.pt"
                if not Path(cp_weights).exists():
                    cp_weights = "weights/yolo11m-seg.pt"
                if not Path(cd_weights).exists():
                    cd_weights = "weights/cardd-yolov8s-seg.pt"

                s2_settings = Stage2Settings(
                    carparts_model_path=cp_weights,
                    cardd_model_path=cd_weights,
                    som_output_dir=claim_scratch_dir / "som",
                    inference_imgsz=opts.get("imgsz", 640),
                    part_min_confidence=opts.get("part_min_conf", 0.35),
                    damage_min_confidence_global=opts.get("damage_min_conf", 0.30),
                )

                s2_orch = get_stage2_orchestrator(
                    db_session=self.db,
                    redis_client=self.redis,
                    settings=s2_settings,
                )

                stage3_payload = await s2_orch.execute(s2_payload)
                s2_audit.status = "PASSED"
                billed_parts = [p.canonical_part_key for p in stage3_payload.grounded_parts if getattr(p, "is_claimed", True)]
                quarantined = [p.canonical_part_key for p in getattr(stage3_payload, "unclaimed_preexisting_parts", [])]
                s2_audit.outputs_summary = {
                    "grounded_parts_count": len(stage3_payload.grounded_parts),
                    "billed_parts": billed_parts,
                    "quarantined_parts": quarantined,
                }
                # Collect rendered annotated artifacts and damage summaries
                som_crops = []
                raw_crops = []
                full_annotated = []
                damage_details = []
                for p in stage3_payload.grounded_parts:
                    if getattr(p, "som_annotated_crop_path", None):
                        som_crops.append(str(p.som_annotated_crop_path))
                    if getattr(p, "som_raw_crop_path", None):
                        raw_crops.append(str(p.som_raw_crop_path))
                    if getattr(p, "som_full_annotated_path", None):
                        full_annotated.append(str(p.som_full_annotated_path))
                    damage_details.append({
                        "part_key": p.canonical_part_key,
                        "display_name": getattr(p, "display_part_name", p.canonical_part_key),
                        "oem_number": getattr(p, "oem_part_number", "OEM-SCHEDULE-01"),
                        "material": getattr(p, "part_material", "metal"),
                        "damage_class": getattr(p, "primary_damage_class", "dent"),
                        "damage_confidence": getattr(p, "damage_confidence", 0.0),
                        "iop_percentage": getattr(p, "iop_percentage", getattr(p, "final_iop_ratio", 0.0) * 100.0),
                        "is_repairable": getattr(p, "is_repairable", True),
                        "som_crop": str(getattr(p, "som_annotated_crop_path", "")),
                        "raw_crop": str(getattr(p, "som_raw_crop_path", "")),
                        "full_annotated": str(getattr(p, "som_full_annotated_path", "")),
                    })

                s2_audit.artifacts["som_crops"] = som_crops
                s2_audit.artifacts["raw_crops"] = raw_crops
                s2_audit.artifacts["annotated_damage_images"] = full_annotated
                s2_audit.artifacts["damage_details"] = damage_details

                audit.generated_artifacts["som_crops"] = som_crops
                audit.generated_artifacts["raw_crops"] = raw_crops
                if full_annotated:
                    audit.generated_artifacts["annotated_damage_images"] = full_annotated
                audit.damage_report = damage_details

                s2_audit.decision_reasoning = (
                    f"Grounded {len(billed_parts)} claimed damaged parts for billing; "
                    f"quarantined {len(quarantined)} background defects."
                )
                await _notify("STAGE_2", "PASSED", s2_audit.outputs_summary)

            except Stage2ClaimedDamageNotFoundError as cdnf:
                s2_audit.status = "ESCALATED"
                s2_audit.escalation_code = "ESC-07"
                s2_audit.decision_reasoning = str(cdnf)
                s2_audit.failure_codes = ["ESC-07_CLAIMED_DAMAGE_NOT_FOUND"]
            except Stage2Error as s2e:
                s2_audit.status = "ESCALATED"
                s2_audit.escalation_code = s2e.escalation_code
                s2_audit.decision_reasoning = str(s2e)
                s2_audit.failure_codes = s2e.failure_codes or [s2e.escalation_code]
            except Exception as s2_err:
                s2_audit.status = "FAILED"
                s2_audit.failure_codes.append(f"STAGE2_EXCEPTION: {str(s2_err)}")
                s2_audit.summary_message = str(s2_err)

        s2_audit.latency_ms = round((time.perf_counter() - t0_s2) * 1000.0, 2)
        s2_audit.completed_at = self._now_iso()
        audit.stage_audits["stage_2"] = s2_audit

        if stage3_payload is None or not getattr(stage3_payload, "grounded_parts", None):
            if not opts.get("force_continue", False):
                audit.final_verdict = f"ESCALATED_{s2_audit.escalation_code or 'STAGE2'}"
                audit.escalation_code = s2_audit.escalation_code or "ESC-07"
                audit.total_execution_ms = round((time.perf_counter() - t_global_start) * 1000.0, 2)
                audit.completed_at = self._now_iso()
                return audit

        # ----------------------------------------------------------------------
        # STAGE 3: Set-of-Marks VLM Damage Inspection & Depth Grading
        # ----------------------------------------------------------------------
        t0_s3 = time.perf_counter()
        s3_start = self._now_iso()
        s3_audit = StageAuditDTO(
            stage_name="STAGE_3_VLM_INSPECTION",
            status="PENDING",
            latency_ms=0.0,
            started_at=s3_start,
            completed_at="",
            inputs_summary={"grounded_parts_count": len(getattr(stage3_payload, "grounded_parts", []) or [])},
        )

        stage4_payload = None
        bypass_stage3 = "stage_3" in bypass_set or opts.get("bypass_stage_3", False)

        if bypass_stage3 or stage3_payload is None:
            s3_audit.status = "BYPASSED"
            s3_audit.decision_reasoning = "Stage 3 VLM inspection bypassed; auto-approving candidate parts."
            from app.domain.vlm_damage_inspection.schemas import Stage4HandoffPayload, VerifiedDamagedPart, DepthGrade
            parts_to_verify = getattr(stage3_payload, "grounded_parts", []) if stage3_payload else []
            v_parts = []
            for gp in parts_to_verify:
                v_parts.append(
                    VerifiedDamagedPart(
                        canonical_part_key=gp.canonical_part_key,
                        raw_detected_part_classes=gp.raw_detected_part_classes,
                        side_resolution_method=gp.side_resolution_method,
                        display_part_name=gp.display_part_name,
                        oem_part_number=gp.oem_part_number,
                        part_material=gp.part_material,
                        is_repairable=gp.is_repairable,
                        is_safety_critical=gp.is_safety_critical,
                        detected_damage_classes=gp.detected_damage_classes,
                        primary_damage_class=gp.primary_damage_class,
                        final_iop_ratio=gp.final_iop_ratio,
                        iop_percentage=gp.iop_percentage,
                        iop_estimation_method=gp.iop_estimation_method,
                        zoom_clipped_frames_filtered=gp.zoom_clipped_frames_filtered,
                        persistence_frame_count=gp.persistence_frame_count,
                        part_confidence=gp.part_confidence,
                        damage_confidence=gp.damage_confidence,
                        area_measurement_keyframe=gp.area_measurement_keyframe,
                        vlm_closeup_keyframe=gp.vlm_closeup_keyframe,
                        som_annotated_crop_path=gp.som_annotated_crop_path,
                        som_raw_crop_path=gp.som_raw_crop_path,
                        depth_grade=DepthGrade.L2_BASECOAT_SCRATCH if gp.primary_damage_class == "scratch" else DepthGrade.L3_SHALLOW_DENT_PDR,
                        vlm_confidence=0.95,
                        visual_reasoning_short="Bypass synthetic verification.",
                        is_claimed=True,
                    )
                )
            stage4_payload = Stage4HandoffPayload(
                claim_id=claim_uuid,
                policy_id=policy_id,
                registration_number=getattr(db_policy, "registration_number", "MH12DE1433"),
                make=getattr(db_policy, "make", "Hyundai"),
                model=getattr(db_policy, "model", "Creta"),
                verified_parts=v_parts,
            )
            s3_audit.outputs_summary = {"verified_parts_count": len(v_parts), "bypassed": True}
            await _notify("STAGE_3", "BYPASSED", s3_audit.outputs_summary)

        else:
            try:
                from app.domain.vlm_damage_inspection.orchestrator import Stage3VLMOrchestrator
                from app.domain.vlm_damage_inspection.config import Stage3Settings
                from app.domain.vlm_damage_inspection.adapters.factory import get_vlm_adapter
                from app.domain.vlm_damage_inspection.exceptions import (
                    Stage3InspectionError,
                    Stage3NoRealDamageDetectedError,
                    Stage3RustOrOxidationError,
                    Stage3StructuralMisalignmentError,
                )

                vlm_prov = opts.get("vlm_provider", self.vlm_provider)
                s3_settings = Stage3Settings(vlm_provider=vlm_prov)
                adapter = get_vlm_adapter(s3_settings, provider_override=vlm_prov)

                s3_orch = Stage3VLMOrchestrator(settings=s3_settings, adapter=adapter)
                stage4_payload = await s3_orch.inspect_claim(stage3_payload)

                s3_audit.status = "PASSED"
                for vp in stage4_payload.verified_parts:
                    for d_item in audit.damage_report:
                        if d_item["part_key"] == vp.canonical_part_key:
                            d_item["depth_grade"] = str(vp.depth_grade.value)
                            d_item["vlm_confidence"] = getattr(vp, "vlm_confidence", 0.90)

                s3_audit.outputs_summary = {
                    "verified_parts_count": len(stage4_payload.verified_parts),
                    "quarantined_parts_count": len(stage4_payload.quarantined_parts),
                    "verified_keys": [p.canonical_part_key for p in stage4_payload.verified_parts],
                    "depth_grades": {p.canonical_part_key: str(p.depth_grade.value) for p in stage4_payload.verified_parts},
                }
                s3_audit.decision_reasoning = (
                    f"VLM verified {len(stage4_payload.verified_parts)} physically real damages; "
                    f"filtered {len(stage4_payload.quarantined_parts)} superficial glare/contaminants."
                )
                await _notify("STAGE_3", "PASSED", s3_audit.outputs_summary)

            except Stage3RustOrOxidationError as rfe:
                s3_audit.status = "ESCALATED"
                s3_audit.escalation_code = "ESC-04"
                s3_audit.decision_reasoning = f"Pre-existing rust/oxidation detected: {rfe}"
                s3_audit.failure_codes = ["ESC-04_PREEXISTING_CORROSION"]
            except Stage3StructuralMisalignmentError as sme:
                s3_audit.status = "ESCALATED"
                s3_audit.escalation_code = "ESC-06"
                s3_audit.decision_reasoning = f"Structural frame gap misalignment: {sme}"
                s3_audit.failure_codes = ["ESC-06_STRUCTURAL_HAZARD"]
            except Stage3NoRealDamageDetectedError as nde:
                s3_audit.status = "ESCALATED"
                s3_audit.escalation_code = "ESC-07"
                s3_audit.decision_reasoning = f"Zero real physical damage detected: {nde}"
                s3_audit.failure_codes = ["ESC-07_NO_REAL_DAMAGE"]
            except Stage3InspectionError as s3e:
                s3_audit.status = "ESCALATED"
                s3_audit.escalation_code = getattr(s3e, "escalation_code", "ESC-07")
                s3_audit.decision_reasoning = str(s3e)
                s3_audit.failure_codes = [getattr(s3e, "failure_code", "S3_ERROR")]
            except Exception as s3_err:
                s3_audit.status = "FAILED"
                s3_audit.failure_codes.append(f"STAGE3_EXCEPTION: {str(s3_err)}")
                s3_audit.summary_message = str(s3_err)

        s3_audit.latency_ms = round((time.perf_counter() - t0_s3) * 1000.0, 2)
        s3_audit.completed_at = self._now_iso()
        audit.stage_audits["stage_3"] = s3_audit

        if stage4_payload is None or not getattr(stage4_payload, "verified_parts", None):
            if not opts.get("force_continue", False):
                audit.final_verdict = f"ESCALATED_{s3_audit.escalation_code or 'STAGE3'}"
                audit.escalation_code = s3_audit.escalation_code or "ESC-07"
                audit.total_execution_ms = round((time.perf_counter() - t_global_start) * 1000.0, 2)
                audit.completed_at = self._now_iso()
                return audit

        # ----------------------------------------------------------------------
        # STAGE 4: Deterministic Actuarial Pricing Engine
        # ----------------------------------------------------------------------
        t0_s4 = time.perf_counter()
        s4_start = self._now_iso()
        s4_audit = StageAuditDTO(
            stage_name="STAGE_4_ACTUARIAL_PRICING",
            status="PENDING",
            latency_ms=0.0,
            started_at=s4_start,
            completed_at="",
            inputs_summary={"verified_parts_count": len(getattr(stage4_payload, "verified_parts", []) or [])},
        )

        actuarial_estimate = None
        bypass_stage4 = "stage_4" in bypass_set or opts.get("bypass_stage_4", False)

        if bypass_stage4 or stage4_payload is None:
            s4_audit.status = "BYPASSED"
            s4_audit.decision_reasoning = "Stage 4 Actuarial Pricing bypassed."
        else:
            try:
                from app.domain.actuarial_pricing.orchestrator import Stage4ActuarialOrchestrator
                from app.domain.actuarial_pricing.exceptions import (
                    ActuarialPricingError,
                    Stage4DoubleDippingFraudError,
                    Stage4FinancialCeilingExceededError,
                )

                s4_orch = Stage4ActuarialOrchestrator(
                    session=self.db,
                    redis_manager=self.redis,
                )
                actuarial_estimate = await s4_orch.execute(stage4_payload)

                s4_audit.status = "PASSED"
                s4_audit.outputs_summary = {
                    "gross_repair_inr": str(actuarial_estimate.summary.gross_garage_repair_inr),
                    "total_depreciation_inr": str(actuarial_estimate.summary.total_depreciation_inr),
                    "net_liability_inr": str(actuarial_estimate.summary.net_claim_liability_inr),
                    "initial_offer_inr": str(actuarial_estimate.settlement_band.initial_offer_inr),
                    "walkaway_cap_inr": str(actuarial_estimate.settlement_band.walkaway_cap_inr),
                    "ncb_recommendation": str(actuarial_estimate.ncb_advisory.recommendation.value),
                }
                s4_audit.decision_reasoning = (
                    f"Deterministic statutory assessment: Gross repair ₹{actuarial_estimate.summary.gross_garage_repair_inr:,.2f}, "
                    f"Net claim liability ₹{actuarial_estimate.summary.net_claim_liability_inr:,.2f}. "
                    f"NCB recommendation: {actuarial_estimate.ncb_advisory.recommendation.value}."
                )
                audit.financial_summary = s4_audit.outputs_summary
                await _notify("STAGE_4", "PASSED", s4_audit.outputs_summary)

            except Stage4DoubleDippingFraudError as dfe:
                s4_audit.status = "ESCALATED"
                s4_audit.escalation_code = "ESC-03"
                s4_audit.decision_reasoning = f"Prior unrepaired cash claim detected on panel: {dfe}"
                s4_audit.failure_codes = ["ESC-03_DOUBLE_DIPPING_FRAUD"]
            except Stage4FinancialCeilingExceededError as cfe:
                s4_audit.status = "ESCALATED"
                s4_audit.escalation_code = "ESC-08"
                s4_audit.decision_reasoning = f"Autonomous financial ceiling (₹25,000) exceeded: {cfe}"
                s4_audit.failure_codes = ["ESC-08_AUTONOMOUS_CEILING_BREACH"]
            except ActuarialPricingError as ape:
                s4_audit.status = "ESCALATED"
                s4_audit.escalation_code = ape.code
                s4_audit.decision_reasoning = str(ape)
                s4_audit.failure_codes = [ape.code]
            except Exception as s4_err:
                s4_audit.status = "FAILED"
                s4_audit.failure_codes.append(f"STAGE4_EXCEPTION: {str(s4_err)}")
                s4_audit.summary_message = str(s4_err)

        s4_audit.latency_ms = round((time.perf_counter() - t0_s4) * 1000.0, 2)
        s4_audit.completed_at = self._now_iso()
        audit.stage_audits["stage_4"] = s4_audit

        if actuarial_estimate is None or getattr(actuarial_estimate, "is_ceiling_breached", False):
            if not opts.get("force_continue", False):
                audit.final_verdict = f"ESCALATED_{s4_audit.escalation_code or 'STAGE4'}"
                audit.escalation_code = s4_audit.escalation_code or "ESC-08"
                audit.total_execution_ms = round((time.perf_counter() - t_global_start) * 1000.0, 2)
                audit.completed_at = self._now_iso()
                return audit

        # ----------------------------------------------------------------------
        # STAGE 5: Negotiation Chatbot FSM & HMAC Signing
        # ----------------------------------------------------------------------
        t0_s5 = time.perf_counter()
        s5_start = self._now_iso()
        s5_audit = StageAuditDTO(
            stage_name="STAGE_5_NEGOTIATION_CHATBOT",
            status="PENDING",
            latency_ms=0.0,
            started_at=s5_start,
            completed_at="",
            inputs_summary={"strategy": negotiation_strategy},
        )

        negotiation_session = None
        active_offer_card = None
        bypass_stage5 = "stage_5" in bypass_set or opts.get("bypass_stage_5", False)

        if bypass_stage5 or actuarial_estimate is None:
            s5_audit.status = "BYPASSED"
            s5_audit.decision_reasoning = "Stage 5 negotiation chatbot bypassed."
        else:
            try:
                from app.domain.negotiation_chatbot.orchestrator import Stage5NegotiationOrchestrator
                from app.domain.negotiation_chatbot.schemas import (
                    ClaimantMessageDTO,
                    OfferCardDTO,
                )

                stage5_orch = Stage5NegotiationOrchestrator(
                    db_session=self.db,
                    redis_mgr=self.redis,
                )
                negotiation_session = await stage5_orch.initialize_session(actuarial_estimate)
                active_offer_card = negotiation_session.active_offer_card

                turns_executed = []

                if negotiation_strategy == "immediate_accept":
                    # Directly accept initial offer
                    s5_audit.decision_reasoning = "Strategy: Accepted initial offer card immediately."

                elif negotiation_strategy == "reject_to_surveyor":
                    # Reject offer to escalate to human surveyor
                    s5_audit.decision_reasoning = "Strategy: Claimant elected garage repair routing / rejected offer."

                elif negotiation_strategy == "counter_then_accept":
                    # Send realistic counter-offer
                    initial_amt = active_offer_card.amount_inr
                    target_amt = actuarial_estimate.settlement_band.target_settlement_inr
                    counter_val = min(target_amt + Decimal("500.00"), actuarial_estimate.settlement_band.walkaway_cap_inr)

                    msg_dto = ClaimantMessageDTO(
                        message=f"I got a local body shop quote for ₹{counter_val:,.2f}. Can you please increase your offer?",
                        counteroffer_inr=counter_val,
                    )
                    turn_result = await stage5_orch.process_claimant_turn(claim_uuid, msg_dto)
                    active_offer_card = turn_result.offer_card
                    turns_executed.append({
                        "round_num": turn_result.round_num,
                        "claimant_message": msg_dto.message,
                        "counteroffer_inr": str(counter_val),
                        "chatbot_reply": turn_result.chatbot_reply,
                        "conceded_amount_inr": str(active_offer_card.amount_inr),
                    })
                    s5_audit.decision_reasoning = (
                        f"Executed Round 1 negotiation: Claimant requested ₹{counter_val}, "
                        f"AI adjusted offer to ₹{active_offer_card.amount_inr}."
                    )

                elif negotiation_strategy == "interactive" and interactive_negotiation_handler:
                    # Interactive hook for terminal CLI or Web UI
                    step_data = {
                        "claim_id": str(claim_uuid),
                        "current_round": negotiation_session.current_round,
                        "active_offer": active_offer_card.to_dict(),
                        "settlement_band": actuarial_estimate.settlement_band.to_dict(),
                    }
                    user_action = await interactive_negotiation_handler(step_data)
                    action_type = user_action.get("action", "accept")

                    if action_type == "counter":
                        counter_inr = Decimal(str(user_action.get("counteroffer_inr", active_offer_card.amount_inr)))
                        msg_dto = ClaimantMessageDTO(
                            message=user_action.get("message", "Counter-offer"),
                            counteroffer_inr=counter_inr,
                        )
                        turn_result = await stage5_orch.process_claimant_turn(claim_uuid, msg_dto)
                        active_offer_card = turn_result.offer_card
                        turns_executed.append({
                            "round_num": turn_result.round_num,
                            "claimant_message": msg_dto.message,
                            "chatbot_reply": turn_result.chatbot_reply,
                            "offered_amount_inr": str(active_offer_card.amount_inr),
                        })
                    elif action_type == "reject":
                        negotiation_strategy = "reject_to_surveyor"

                s5_audit.status = "PASSED"
                s5_audit.outputs_summary = {
                    "final_offer_inr": str(active_offer_card.amount_inr) if active_offer_card else None,
                    "hmac_signature": active_offer_card.hmac_signature if active_offer_card else None,
                    "turns_count": len(turns_executed),
                    "turns": turns_executed,
                }
                audit.negotiation_summary = s5_audit.outputs_summary
                await _notify("STAGE_5", "PASSED", s5_audit.outputs_summary)

            except Exception as s5_err:
                s5_audit.status = "FAILED"
                s5_audit.failure_codes.append(f"STAGE5_EXCEPTION: {str(s5_err)}")
                s5_audit.summary_message = str(s5_err)

        s5_audit.latency_ms = round((time.perf_counter() - t0_s5) * 1000.0, 2)
        s5_audit.completed_at = self._now_iso()
        audit.stage_audits["stage_5"] = s5_audit

        # ----------------------------------------------------------------------
        # STAGE 6: Settlement Router, Apportionment & Dossier / Voucher PDF
        # ----------------------------------------------------------------------
        t0_s6 = time.perf_counter()
        s6_start = self._now_iso()
        s6_audit = StageAuditDTO(
            stage_name="STAGE_6_SETTLEMENT_ESCALATION",
            status="PENDING",
            latency_ms=0.0,
            started_at=s6_start,
            completed_at="",
        )

        voucher = None
        dossier = None
        pdf_path = None

        try:
            from app.domain.settlement_escalation.orchestrator import Stage6SettlementOrchestrator
            from app.domain.settlement_escalation.pdf_service import reportlab_pdf_service

            stage6_orch = Stage6SettlementOrchestrator(
                db_session=self.db,
                redis_mgr=self.redis,
            )

            if negotiation_strategy == "reject_to_surveyor":
                # Route to human surveyor desk
                dossier = await stage6_orch.escalate_claim(
                    claim_id=claim_uuid,
                    escalation_code="ESC-09",
                    escalation_reason="Claimant rejected cash settlement offer; requested network workshop routing.",
                )
                pdf_bytes = reportlab_pdf_service.generate_adjuster_dossier_pdf(dossier)
                pdf_file = claim_scratch_dir / f"dossier_{claim_uuid}.pdf"
                pdf_file.write_bytes(pdf_bytes)
                pdf_path = str(pdf_file)

                s6_audit.status = "ESCALATED_HUMAN"
                s6_audit.outputs_summary = {
                    "action": "ESCALATED_HUMAN_REVIEW",
                    "dossier_id": dossier.dossier_id,
                    "pdf_path": pdf_path,
                }
                s6_audit.decision_reasoning = (
                    f"Compiled official Surveyor Claims Review Dossier ({dossier.dossier_id}) "
                    f"and generated printable PDF."
                )
                audit.final_verdict = "ESCALATED_HUMAN"
                audit.generated_artifacts["dossier_pdf"] = pdf_path
                await _notify("STAGE_6", "ESCALATED_HUMAN", s6_audit.outputs_summary)

            else:
                # Settle cash claim with UPI voucher
                if active_offer_card is None:
                    # Fallback signed card if Stage 5 was bypassed
                    from app.domain.negotiation_chatbot.hmac_signer import hmac_offer_signer
                    from app.domain.negotiation_chatbot.schemas import OfferCardDTO
                    fallback_amt = Decimal("8500.00")
                    exp = hmac_offer_signer.generate_expiration_epoch()
                    sig = hmac_offer_signer.sign_offer(claim_uuid, 0, fallback_amt, exp)
                    active_offer_card = OfferCardDTO(
                        claim_id=claim_uuid,
                        round_num=0,
                        amount_inr=fallback_amt,
                        formatted_amount=f"₹{fallback_amt:,.2f}",
                        expires_at_epoch=exp,
                        hmac_signature=sig,
                    )

                voucher = await stage6_orch.finalize_settlement(
                    claim_id=claim_uuid,
                    accepted_offer=active_offer_card,
                    beneficiary_upi_id=beneficiary_upi,
                )
                pdf_bytes = reportlab_pdf_service.generate_settlement_voucher_pdf(voucher)
                pdf_file = claim_scratch_dir / f"voucher_{claim_uuid}.pdf"
                pdf_file.write_bytes(pdf_bytes)
                pdf_path = str(pdf_file)

                s6_audit.status = "SETTLED_CASH"
                s6_audit.outputs_summary = {
                    "action": "SETTLED_CASH_IN_LIEU",
                    "voucher_id": voucher.voucher_id,
                    "settled_amount_inr": str(voucher.settled_amount_inr),
                    "beneficiary_upi_id": voucher.beneficiary_upi_id,
                    "apportioned_parts": [p.canonical_part_key for p in voucher.apportioned_parts],
                    "pdf_path": pdf_path,
                }
                s6_audit.decision_reasoning = (
                    f"Issued instant cash voucher {voucher.voucher_id} for ₹{voucher.settled_amount_inr:,.2f} "
                    f"with penny-balanced apportionment across {len(voucher.apportioned_parts)} parts."
                )
                audit.final_verdict = "SETTLED_CASH"
                audit.generated_artifacts["voucher_pdf"] = pdf_path
                await _notify("STAGE_6", "SETTLED_CASH", s6_audit.outputs_summary)

        except Exception as s6_err:
            s6_audit.status = "FAILED"
            s6_audit.failure_codes.append(f"STAGE6_EXCEPTION: {str(s6_err)}")
            s6_audit.summary_message = str(s6_err)
            audit.final_verdict = "REJECTED_STAGE6_ERROR"

        s6_audit.latency_ms = round((time.perf_counter() - t0_s6) * 1000.0, 2)
        s6_audit.completed_at = self._now_iso()
        audit.stage_audits["stage_6"] = s6_audit

        # Finalize master audit
        audit.total_execution_ms = round((time.perf_counter() - t_global_start) * 1000.0, 2)
        audit.completed_at = self._now_iso()

        # Save audit trail to disk
        audit_file = claim_scratch_dir / "audit_trail.json"
        audit_file.write_text(audit.to_json(indent=2))
        audit.generated_artifacts["audit_trail_json"] = str(audit_file)

        return audit
