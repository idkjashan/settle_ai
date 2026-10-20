"""
evals/e2e_scenario_eval_harness.py
Comprehensive End-to-End Evaluation Harness for Auto-Settle AI.

Executes test scenarios through all active pipeline stages:
  Stage 0: Dual-Modality Fast-Fail Gate (Container Forensics / Photo Forensics & Visual Quality)
  System 1: Dynamic Claim Intent Grounder (FastEmbed ONNX NLP & Taxonomy Registry)
  Stage 1: Vehicle Identity & Continuity Grounding (CutDetector, Plate OCR, Color HSV Grounding, ByteTrack)
  Stage 2: Conditioned Dual-Mask Segmentation & Damage Quarantine (Carparts-Seg, CarDD-Seg, Shapely IoP, OEM Catalogue)

Produces detailed stage-by-stage diagnostics, latency breakdowns, and failure analysis.
"""
import argparse
import asyncio
from datetime import date, datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional
import uuid

import cv2
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import logger
from app.infrastructure.db.models import Claim, InsuredPolicy, OemPart
from app.domain.fast_fail_gate.schemas import (
    CaptureModality,
    CaptureSource,
    FastFailFailureCode,
    FastFailResponseDTO,
)
from app.domain.fast_fail_gate.container_forensics import (
    container_forensics_validator,
    validate_photo_pack,
)
from app.domain.fast_fail_gate.visual_quality_gate import (
    visual_quality_validator,
    validate_photos,
)
from app.domain.vehicle_identity_continuity.orchestrator import (
    VehicleIdentityContinuityOrchestrator,
)
from app.domain.vehicle_identity_continuity.schemas import (
    Stage2HandoffPayload,
    VehicleContinuityTelemetryDTO,
    PolicyGroundingContext,
)
from app.domain.claim_intent.intent_grounder import get_claim_intent_grounder
from app.domain.claim_intent.schemas import ClaimIntent
from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.orchestrator import (
    DualMaskSegmentationOrchestrator,
    get_stage2_orchestrator,
)
from app.domain.dual_mask_segmentation.schemas import Stage3HandoffPayload
from app.domain.dual_mask_segmentation.exceptions import (
    Stage2Error,
    Stage2ModelCompatibilityError,
    Stage2ClaimedDamageNotFoundError,
)
from app.infrastructure.db.repositories import PolicyRepository, ClaimRepository
from unittest.mock import AsyncMock
from app.infrastructure.cache.redis_manager import redis_manager
from tests.in_memory_db import FakeAsyncSession, in_memory_db


# Additional helper to seed scenario-specific policies into in_memory_db
def seed_scenario_policies():
    """Seeds policies for vehicles used across test scenarios if not already present."""
    scenario_policies = {
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
        "POL-FERRARI-013": InsuredPolicy(
            policy_id="POL-FERRARI-013",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="3PEDAL",
            vin_last_6="11445D",
            make="Ferrari",
            model="360",
            manufacturing_year=1999,
            registered_color="SILVER",
            registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 50, "v_min": 100, "v_max": 220},
            paint_type="metallic",
            zero_dep_addon=False,
            compulsory_deductible_inr=Decimal("5000.00"),
            estimated_ncb_loss_inr=Decimal("12000.00"),
        ),
        "POL-WRX-014": InsuredPolicy(
            policy_id="POL-WRX-014",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="MH12DE1433",
            vin_last_6="22556E",
            make="Subaru",
            model="Impreza",
            manufacturing_year=2002,
            registered_color="BLUE",
            registered_color_hsv={"h_min": 100, "h_max": 130, "s_min": 80, "s_max": 255, "v_min": 50, "v_max": 255},
            paint_type="metallic",
            zero_dep_addon=True,
            compulsory_deductible_inr=Decimal("1000.00"),
            estimated_ncb_loss_inr=Decimal("3000.00"),
        ),
        "POL-MUSTANG-015": InsuredPolicy(
            policy_id="POL-MUSTANG-015",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="MH12DE1433",
            vin_last_6="33667F",
            make="Ford",
            model="Mustang",
            manufacturing_year=2018,
            registered_color="GREY",
            registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 50, "v_min": 40, "v_max": 160},
            paint_type="metallic",
            zero_dep_addon=True,
            compulsory_deductible_inr=Decimal("1500.00"),
            estimated_ncb_loss_inr=Decimal("4500.00"),
        ),
        "POL-LEXUS-016": InsuredPolicy(
            policy_id="POL-LEXUS-016",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="LELB09",
            vin_last_6="44778G",
            make="Lexus",
            model="NX",
            manufacturing_year=2022,
            registered_color="BLACK",
            registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 55, "v_min": 0, "v_max": 100},
            paint_type="metallic",
            zero_dep_addon=True,
            compulsory_deductible_inr=Decimal("2000.00"),
            estimated_ncb_loss_inr=Decimal("5000.00"),
        ),
        "POL-ACCORD-017": InsuredPolicy(
            policy_id="POL-ACCORD-017",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="CJ09025",
            vin_last_6="55889H",
            make="Honda",
            model="Accord",
            manufacturing_year=2007,
            registered_color="BLUE",
            registered_color_hsv={"h_min": 100, "h_max": 130, "s_min": 80, "s_max": 255, "v_min": 50, "v_max": 255},
            paint_type="metallic",
            zero_dep_addon=False,
            compulsory_deductible_inr=Decimal("1000.00"),
            estimated_ncb_loss_inr=Decimal("2000.00"),
        ),
        "POL-MERC-018": InsuredPolicy(
            policy_id="POL-MERC-018",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="LARNLEED",
            vin_last_6="66990I",
            make="Mercedes-Benz",
            model="E350",
            manufacturing_year=2011,
            registered_color="SILVER",
            registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 50, "v_min": 100, "v_max": 220},
            paint_type="metallic",
            zero_dep_addon=True,
            compulsory_deductible_inr=Decimal("2500.00"),
            estimated_ncb_loss_inr=Decimal("6000.00"),
        ),
    }
    for pid, pol in scenario_policies.items():
        if pid not in in_memory_db.policies:
            in_memory_db.policies[pid] = pol


class E2EScenarioEvaluator:
    """Orchestrates end-to-end evaluation for individual motor claims scenarios."""

    def __init__(self):
        seed_scenario_policies()
        self.grounder = get_claim_intent_grounder()

    async def evaluate_scenario(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluates a single scenario across all pipeline stages."""
        scenario_id = scenario["scenario_id"]
        name = scenario["name"]
        modality = scenario.get("modality", "video")
        media_path = scenario["media_path"]
        claim_description = scenario.get("claim_description", "")
        policy_id = scenario.get("policy_id", "POL-HAPPY-001")
        claim_id = uuid.uuid4()

        result = {
            "scenario_id": scenario_id,
            "name": name,
            "modality": modality,
            "policy_id": policy_id,
            "claim_id": str(claim_id),
            "stages": {},
            "verdict": "FAIL",
            "divergence_stage": None,
            "divergence_reason": None,
        }

        db_session = FakeAsyncSession()
        redis_client = AsyncMock()
        redis_client.publish = AsyncMock(return_value=1)
        policy_repo = PolicyRepository(db_session)
        claim_repo = ClaimRepository(db_session)

        # ---------------------------------------------------------
        # STAGE 0: Fast-Fail Gate
        # ---------------------------------------------------------
        t0_s0 = time.perf_counter()
        s0_info = {"passed": False, "failure_codes": [], "latency_ms": 0.0}

        try:
            if modality == "video":
                v_path = Path(media_path)
                if not v_path.exists():
                    s0_info["failure_codes"].append(f"MEDIA_FILE_NOT_FOUND: {media_path}")
                else:
                    file_size = v_path.stat().st_size
                    c_rep = container_forensics_validator.validate(v_path, f"sha_{scenario_id}", file_size)
                    v_rep = visual_quality_validator.validate(v_path, c_rep)
                    s0_passed = c_rep.passed and v_rep.passed
                    s0_info["passed"] = s0_passed
                    s0_info["failure_codes"] = list(set((c_rep.failure_codes or []) + (v_rep.failure_codes or [])))
                    s0_info["details"] = {
                        "width": c_rep.width,
                        "height": c_rep.height,
                        "fps": c_rep.effective_fps,
                        "duration_sec": c_rep.duration_sec,
                        "mean_luminance": getattr(v_rep, "mean_luminance_aggregate", None),
                        "mean_sharpness": getattr(v_rep, "mean_sharpness_aggregate", None),
                    }
            elif modality == "photo_pack":
                photo_paths = [Path(p) for p in media_path] if isinstance(media_path, list) else [Path(media_path)]
                p_rep = validate_photo_pack(photo_paths)
                v_rep = validate_photos(photo_paths)
                s0_passed = p_rep.passed and v_rep.passed
                s0_info["passed"] = s0_passed
                s0_info["failure_codes"] = list(set((p_rep.failure_codes or []) + (v_rep.failure_codes or [])))
                s0_info["details"] = {
                    "photo_count": p_rep.photo_count,
                    "resolution": str(p_rep.resolutions[0]) if p_rep.resolutions else "unknown",
                    "mean_sharpness": getattr(v_rep, "mean_sharpness_aggregate", None),
                    "mean_luminance": getattr(v_rep, "mean_luminance_aggregate", None),
                }
            else:
                s0_info["failure_codes"].append(f"UNKNOWN_MODALITY: {modality}")
        except Exception as e:
            s0_info["failure_codes"].append(f"STAGE0_EXCEPTION: {str(e)}")

        s0_info["latency_ms"] = round((time.perf_counter() - t0_s0) * 1000.0, 2)
        result["stages"]["stage_0"] = s0_info

        expected_s0 = scenario.get("expected_stage0_pass", True)
        if s0_info["passed"] != expected_s0:
            result["divergence_stage"] = "STAGE_0"
            result["divergence_reason"] = f"Expected Stage 0 {expected_s0}, got {s0_info['passed']} (Codes: {s0_info['failure_codes']})"
            return result

        if not s0_info["passed"]:
            # Scenario was expected to fail at Stage 0 and correctly failed!
            result["verdict"] = "PASS"
            return result

        # ---------------------------------------------------------
        # SYSTEM 1: Claim Intent Grounding
        # ---------------------------------------------------------
        t0_intent = time.perf_counter()
        intent_info = {"extracted_parts": [], "extracted_damages": [], "latency_ms": 0.0}
        claim_intent: Optional[ClaimIntent] = None

        if claim_description:
            try:
                claim_intent = self.grounder.ground(claim_description)
                intent_info["extracted_parts"] = claim_intent.claimed_parts
                intent_info["extracted_damages"] = claim_intent.claimed_damages
                intent_info["directional_modifiers"] = [
                    getattr(getattr(p, "part", None), "position", None)
                    for p in getattr(claim_intent, "paired_intents", [])
                ]
            except Exception as e:
                intent_info["error"] = str(e)

        intent_info["latency_ms"] = round((time.perf_counter() - t0_intent) * 1000.0, 2)
        result["stages"]["intent_grounding"] = intent_info

        # Verify intent against expectations if specified
        exp_parts = scenario.get("expected_claimed_parts")
        if exp_parts and not any(p in intent_info["extracted_parts"] for p in exp_parts):
            logger.warning(f"Scenario {scenario_id}: Intent extracted {intent_info['extracted_parts']} vs expected {exp_parts}")

        # ---------------------------------------------------------
        # STAGE 1: Vehicle Identity & Continuity Grounding
        # ---------------------------------------------------------
        t0_s1 = time.perf_counter()
        s1_info = {"passed": False, "failure_codes": [], "latency_ms": 0.0}
        telemetry: Optional[VehicleContinuityTelemetryDTO] = None

        stage1_orch = VehicleIdentityContinuityOrchestrator(
            policy_repo=policy_repo,
            claim_repo=claim_repo,
            redis_mgr=redis_client,
        )

        try:
            if modality == "video":
                telemetry = await stage1_orch.execute(
                    claim_id=claim_id,
                    scratch_video_path=Path(media_path),
                    policy_id=policy_id,
                    is_demo_rehearsal=True,
                )
            else:
                photo_paths = [Path(p) for p in media_path] if isinstance(media_path, list) else [Path(media_path)]
                telemetry = await stage1_orch.execute_photo_pack(
                    claim_id=claim_id,
                    photo_paths=photo_paths,
                    policy_id=policy_id,
                    is_demo_rehearsal=True,
                )

            s1_info["passed"] = bool(telemetry and telemetry.passed)
            s1_info["escalation_code"] = telemetry.escalation_code if telemetry else None
            if telemetry and telemetry.tracking_report:
                s1_info["keyframes_count"] = len(telemetry.tracking_report.saved_keyframes)
                s1_info["keyframes_keys"] = list(telemetry.tracking_report.saved_keyframes.keys())
            if telemetry and telemetry.plate_report:
                s1_info["plate_text"] = telemetry.plate_report.extracted_plate
            if telemetry and telemetry.color_report:
                s1_info["color_delta_e"] = telemetry.color_report.delta_e_hsv
        except Exception as e:
            s1_info["failure_codes"].append(f"STAGE1_EXCEPTION: {str(e)}")

        s1_info["latency_ms"] = round((time.perf_counter() - t0_s1) * 1000.0, 2)
        result["stages"]["stage_1"] = s1_info

        expected_s1 = scenario.get("expected_stage1_pass", True)
        if s1_info["passed"] != expected_s1:
            result["divergence_stage"] = "STAGE_1"
            result["divergence_reason"] = (
                f"Expected Stage 1 {expected_s1}, got {s1_info['passed']} "
                f"(Escalation: {s1_info.get('escalation_code')}, Codes: {s1_info['failure_codes']})"
            )
            return result

        if not s1_info["passed"]:
            result["verdict"] = "PASS"
            return result

        # ---------------------------------------------------------
        # STAGE 2: Conditioned Dual-Mask Segmentation
        # ---------------------------------------------------------
        t0_s2 = time.perf_counter()
        s2_info = {"status": "UNKNOWN", "escalation_code": None, "failure_codes": [], "latency_ms": 0.0}

        try:
            ref_path = str(media_path[0]) if isinstance(media_path, list) else str(media_path)
            keyframes_map = {k: str(v) for k, v in telemetry.tracking_report.saved_keyframes.items()}
            for i, p_str in enumerate(getattr(telemetry.tracking_report, "curated_keyframes", []) or [], 1):
                keyframes_map.setdefault(f"keyframe_{i:02d}", str(p_str))
            
            stage2_payload = Stage2HandoffPayload(
                claim_id=claim_id,
                policy_id=policy_id,
                scratch_video_path=ref_path,
                keyframe_paths=keyframes_map,
                vehicle_telemetry=telemetry,
                claim_intent=claim_intent,
            )

            stage2_settings = Stage2Settings(
                carparts_model_path="weights/carparts-yolo11n-seg.pt",
                cardd_model_path="weights/cardd-yolov8s-seg.pt",
                inference_imgsz=1024,
                part_min_confidence=0.35,
                damage_min_confidence_global=0.30,
                high_conf_escalation_floor=0.40,
            )
            stage2_orch = get_stage2_orchestrator(
                db_session=db_session,
                redis_client=redis_client,
                settings=stage2_settings,
            )

            stage3_payload: Stage3HandoffPayload = await stage2_orch.execute(stage2_payload)
            s2_info["status"] = "STAGE_3_VLM_INSPECTION"
            s2_info["grounded_parts_count"] = len(stage3_payload.grounded_parts)
            s2_info["billed_parts"] = [
                p.canonical_part_key for p in stage3_payload.grounded_parts if p.is_claimed
            ]
            s2_info["quarantined_parts"] = [
                p.canonical_part_key for p in stage3_payload.grounded_parts if not p.is_claimed
            ]
        except Stage2ClaimedDamageNotFoundError as cdnf:
            s2_info["status"] = "ESCALATED_ESC_07"
            s2_info["escalation_code"] = "ESC-07"
            s2_info["message"] = str(cdnf)
        except Stage2Error as s2e:
            s2_info["status"] = f"ESCALATED_{s2e.escalation_code or 'UNKNOWN'}"
            s2_info["escalation_code"] = s2e.escalation_code
            s2_info["message"] = str(s2e)
        except Stage2ModelCompatibilityError as s2_compat:
            s2_info["status"] = "REJECTED_STAGE2_ERROR"
            s2_info["failure_codes"].append("S2_MODEL_COMPATIBILITY_ERROR")
            s2_info["message"] = str(s2_compat)
        except Exception as s2_err:
            s2_info["status"] = "REJECTED_STAGE2_ERROR"
            s2_info["failure_codes"].append(f"STAGE2_EXCEPTION: {str(s2_err)}")

        s2_info["latency_ms"] = round((time.perf_counter() - t0_s2) * 1000.0, 2)
        result["stages"]["stage_2"] = s2_info

        # Compare Stage 2 Outcome with Expected
        exp_s2_status = scenario.get("expected_stage2_status", "STAGE_3_VLM_INSPECTION")
        act_status = s2_info.get("status", "")
        act_esc = s2_info.get("escalation_code") or ""

        if exp_s2_status.startswith("ESC-") and (
            exp_s2_status in act_esc
            or act_esc in exp_s2_status
            or exp_s2_status in act_status
            or (exp_s2_status.startswith("ESC-07") and act_esc.startswith("ESC-07"))
        ):
            s2_matches = True
        elif act_status == exp_s2_status:
            s2_matches = True
        else:
            s2_matches = False

        if not s2_matches:
            result["divergence_stage"] = "STAGE_2"
            result["divergence_reason"] = (
                f"Expected Stage 2 status '{exp_s2_status}', got '{s2_info['status']}' "
                f"(Escalation: {s2_info.get('escalation_code')}, Failure codes: {s2_info['failure_codes']})"
            )
            return result

        result["verdict"] = "PASS"
        return result


async def run_evaluation_suite(
    manifest_path: Path,
    target_scenario_id: Optional[str] = None,
    output_dir: Path = Path("evals"),
) -> Dict[str, Any]:
    """Runs evaluation across all scenarios in manifest and prints summary report."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    data = json.loads(manifest_path.read_text())
    scenarios = data if isinstance(data, list) else data.get("scenarios", [])

    if target_scenario_id:
        scenarios = [s for s in scenarios if s.get("scenario_id") == target_scenario_id]
        if not scenarios:
            raise ValueError(f"Scenario ID {target_scenario_id} not found in manifest")

    evaluator = E2EScenarioEvaluator()
    results = []
    pass_count = 0
    fail_count = 0

    print("=" * 105)
    print(f"🚀 AUTO-SETTLE AI — END-TO-END SCENARIO EVALUATION HARNESS ({len(scenarios)} Scenarios)")
    print("=" * 105)
    print(f"{'ID':<7} | {'Scenario Name':<32} | {'Modality':<8} | {'S0':<5} | {'S1':<5} | {'S2':<12} | {'Verdict':<7} | {'Latency':<8}")
    print("-" * 105)

    for sc in scenarios:
        sc_id = sc["scenario_id"]
        sc_name = sc["name"][:30]
        modality = sc.get("modality", "video")

        try:
            res = await evaluator.evaluate_scenario(sc)
        except Exception as e:
            res = {
                "scenario_id": sc_id,
                "name": sc_name,
                "verdict": "FAIL",
                "divergence_stage": "HARNESS_CRASH",
                "divergence_reason": str(e),
                "stages": {},
            }

        results.append(res)
        s0_p = "PASS" if res.get("stages", {}).get("stage_0", {}).get("passed") else "FAIL"
        s1_p = "PASS" if res.get("stages", {}).get("stage_1", {}).get("passed") else "FAIL"
        s2_st = res.get("stages", {}).get("stage_2", {}).get("status", "N/A")[:11]
        verdict = res["verdict"]

        total_lat = sum(
            stage.get("latency_ms", 0.0) for stage in res.get("stages", {}).values() if isinstance(stage, dict)
        )
        lat_str = f"{total_lat:.0f}ms"

        if verdict == "PASS":
            pass_count += 1
            v_color = "\033[92mPASS\033[0m"
        else:
            fail_count += 1
            v_color = "\033[91mFAIL\033[0m"

        print(f"{sc_id:<7} | {sc_name:<32} | {modality:<8} | {s0_p:<5} | {s1_p:<5} | {s2_st:<12} | {v_color:<16} | {lat_str:<8}")
        if verdict != "PASS":
            div_stage = res.get("divergence_stage", "UNKNOWN")
            div_reason = res.get("divergence_reason", "No details")
            print(f"       └── ⚠️ Divergence at [{div_stage}]: {div_reason}")

    print("=" * 105)
    print(f"📊 SUMMARY: {pass_count} Passed, {fail_count} Failed (Total: {len(scenarios)}) — Pass Rate: {pass_count / len(scenarios) * 100:.1f}%")
    print("=" * 105)

    # Save detailed JSON report
    output_dir.mkdir(parents=True, exist_ok=True)
    report_ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"eval_report_{report_ts}.json"
    latest_report_path = output_dir / "eval_report_latest.json"

    report_payload = {
        "timestamp_utc": datetime.utcnow().isoformat(),
        "total_scenarios": len(scenarios),
        "passed": pass_count,
        "failed": fail_count,
        "pass_rate_pct": round(pass_count / len(scenarios) * 100, 2),
        "results": results,
    }

    report_path.write_text(json.dumps(report_payload, indent=2))
    latest_report_path.write_text(json.dumps(report_payload, indent=2))
    print(f"Detailed evaluation report saved to: {report_path}")

    return report_payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto-Settle AI E2E Evaluation Harness")
    parser.add_argument(
        "--manifest",
        type=str,
        default="evals/curated_test_manifest.json",
        help="Path to scenarios manifest JSON",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Target single scenario ID to run (e.g. SC-01)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="evals",
        help="Output directory or report path",
    )
    args = parser.parse_args()

    asyncio.run(
        run_evaluation_suite(
            manifest_path=Path(args.manifest),
            target_scenario_id=args.scenario,
        )
    )
