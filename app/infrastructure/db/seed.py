"""
app/infrastructure/db/seed.py
Database Seeding & Reset Engine for Auto-Settle AI

Clears and seeds:
1. Insured Policies (for the 4 video test vehicles + fast-fail edge cases)
2. OEM Parts Catalogue (Generic universal catalogue + vehicle-specific catalogues)
3. Sample Unrepaired Claim Ledger (for double-claim prevention)
4. Pre-staged Demo Claims (one per authentic video test asset)
5. Video & Keyframe caches for instant testability
"""

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import shutil
import uuid
from typing import Dict, Any, List, Optional

import cv2
from sqlalchemy import select, delete
from app.infrastructure.db.session import engine, async_session_factory
from app.infrastructure.db.models import Base, InsuredPolicy, OemPart, Claim, UnrepairedClaim
from app.infrastructure.cache.redis_manager import redis_manager
from app.domain.negotiation_chatbot.hmac_signer import hmac_offer_signer
from app.domain.negotiation_chatbot.schemas import (
    OfferCardDTO,
    NegotiationRoundState,
    NegotiationTurnDTO,
    NegotiationSessionDTO,
)
from app.domain.settlement_escalation.schemas import (
    ApportionedPartPayoutDTO,
    SettlementVoucherDTO,
)
from app.domain.settlement_escalation.voucher_generator import voucher_generator
from app.domain.settlement_escalation.dossier_builder import dossier_builder
from app.core.logging import logger

# ---------------------------------------------------------------------------
# Predefined Demo IDs
# ---------------------------------------------------------------------------
CLAIM_CRETA_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
CLAIM_COROLLA_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
CLAIM_NEXON_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
CLAIM_CAMRY_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")

# ---------------------------------------------------------------------------
# Canonical 22 OEM Parts Template
# ---------------------------------------------------------------------------
CANONICAL_22_PARTS = [
    ("front_bumper", "Front Bumper Cover", "plastic", Decimal("8800.00"), Decimal("850.00"), Decimal("1100.00"), Decimal("3800.00"), Decimal("800.00"), True, False),
    ("back_bumper", "Rear Bumper Cover", "plastic", Decimal("8200.00"), Decimal("850.00"), Decimal("1100.00"), Decimal("3600.00"), Decimal("800.00"), True, False),
    ("hood", "Front Bonnet / Hood Panel", "metal", Decimal("14200.00"), Decimal("1100.00"), Decimal("1600.00"), Decimal("4800.00"), Decimal("950.00"), True, False),
    ("trunk", "Rear Trunk Lid Panel", "metal", Decimal("13500.00"), Decimal("1150.00"), Decimal("1500.00"), Decimal("4400.00"), Decimal("900.00"), True, False),
    ("tailgate", "Rear Tailgate Assembly", "metal", Decimal("15800.00"), Decimal("1250.00"), Decimal("1600.00"), Decimal("4500.00"), Decimal("900.00"), True, False),
    ("front_left_door", "Front Left Door Panel", "metal", Decimal("11500.00"), Decimal("950.00"), Decimal("1400.00"), Decimal("4200.00"), Decimal("850.00"), True, False),
    ("front_right_door", "Front Right Door Panel", "metal", Decimal("11500.00"), Decimal("950.00"), Decimal("1400.00"), Decimal("4200.00"), Decimal("850.00"), True, False),
    ("front_door", "Front Door Panel (Generic Alias)", "metal", Decimal("11500.00"), Decimal("950.00"), Decimal("1400.00"), Decimal("4200.00"), Decimal("850.00"), True, False),
    ("back_left_door", "Rear Left Door Panel", "metal", Decimal("10800.00"), Decimal("900.00"), Decimal("1350.00"), Decimal("4000.00"), Decimal("850.00"), True, False),
    ("back_right_door", "Rear Right Door Panel", "metal", Decimal("10800.00"), Decimal("900.00"), Decimal("1350.00"), Decimal("4000.00"), Decimal("850.00"), True, False),
    ("back_door", "Rear Door Panel (Generic Alias)", "metal", Decimal("10800.00"), Decimal("900.00"), Decimal("1350.00"), Decimal("4000.00"), Decimal("850.00"), True, False),
    ("left_mirror", "Left Outside Rear View Mirror", "assembly", Decimal("6400.00"), Decimal("450.00"), Decimal("0.00"), Decimal("900.00"), Decimal("400.00"), False, False),
    ("right_mirror", "Right Outside Rear View Mirror", "assembly", Decimal("6400.00"), Decimal("450.00"), Decimal("0.00"), Decimal("900.00"), Decimal("400.00"), False, False),
    ("front_left_light", "Front Left LED Headlamp", "assembly", Decimal("16500.00"), Decimal("650.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, False),
    ("front_right_light", "Front Right LED Headlamp", "assembly", Decimal("16500.00"), Decimal("650.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, False),
    ("front_light", "Front LED Headlamp Assembly (Generic Alias)", "assembly", Decimal("16500.00"), Decimal("650.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, False),
    ("back_left_light", "Rear Left Tail Lamp Assembly", "assembly", Decimal("7200.00"), Decimal("500.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, False),
    ("back_right_light", "Rear Right Tail Lamp Assembly", "assembly", Decimal("7200.00"), Decimal("500.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, False),
    ("back_light", "Rear Tail Lamp Assembly (Generic Alias)", "assembly", Decimal("7200.00"), Decimal("500.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, False),
    ("front_glass", "Front Laminated Windshield", "glass", Decimal("12400.00"), Decimal("1800.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, True),
    ("back_glass", "Rear Heated Windshield Glass", "glass", Decimal("9200.00"), Decimal("1500.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, True),
    ("wheel", "Alloy Wheel & Tire Assembly", "assembly", Decimal("18500.00"), Decimal("600.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, True),
]

HYUNDAI_CRETA_PARTS = [
    (k, n, f"86511-{k[:4].upper()}", mat, c, rr, dent, paint, pdr, rep, safe)
    for (k, n, mat, c, rr, dent, paint, pdr, rep, safe) in CANONICAL_22_PARTS
]

def generate_scaled_parts(make: str, model: str, part_num_prefix: str, multiplier: float) -> list[OemPart]:
    m = Decimal(str(multiplier))
    parts = []
    for (key, name, mat, cost, rr, dent, paint, pdr, rep, safe) in CANONICAL_22_PARTS:
        scaled_pnum = f"{part_num_prefix}-{key[:4].upper()}"
        parts.append(
            OemPart(
                make=make,
                model=model,
                canonical_part_key=key,
                display_part_name=name,
                oem_part_number=scaled_pnum,
                part_material=mat,
                depreciation_rate_non_zero_dep=Decimal("0.00"),
                oem_part_cost_inr=(cost * m).quantize(Decimal("0.01")),
                rr_labour_inr=(rr * m).quantize(Decimal("0.01")),
                denting_base_labour_inr=(dent * m).quantize(Decimal("0.01")),
                full_panel_paint_inr=(paint * m).quantize(Decimal("0.01")),
                pdr_or_polish_flat_inr=(pdr * m).quantize(Decimal("0.01")),
                is_repairable=rep,
                is_safety_critical=safe,
            )
        )
    return parts

# ---------------------------------------------------------------------------
# Telemetry & Negotiation Session Builders
# ---------------------------------------------------------------------------
def _build_telemetry(reg_num: str, color: str, parts_info: list[dict]):
    grounded_parts = []
    verified_parts = []
    for p in parts_info:
        grounded_parts.append({
            "canonical_part_key": p["key"],
            "display_part_name": p["name"],
            "iou": p.get("iou", 0.88),
            "damage_type": p.get("damage", "dent"),
            "damage_confidence": 0.94,
        })
        verified_parts.append({
            "part_name": p["key"],
            "damage_severity": p.get("severity", "MODERATE"),
            "recommended_action": p.get("action", "REPAIR"),
            "confidence": 0.93,
            "visual_reasoning_short": p.get("reason", f"Grounded damage on {p['name']}"),
        })

    return {
        "fast_fail": {
            "tier1_report": {
                "passed": True,
                "policy_status": "ACTIVE",
                "cash_claims_ytd": 0,
                "max_cash_claims_per_year": 2,
                "duration_ms": 12.0,
                "failure_codes": [],
            },
            "container_report": {
                "passed": True,
                "codec_name": "h264",
                "duration_sec": 18.0,
                "effective_fps": 30.0,
                "width": 1280,
                "height": 720,
            },
            "visual_report": {
                "passed": True,
                "mean_luminance_aggregate": 82.0,
                "mean_sharpness_aggregate": 840.0,
            },
            "total_execution_ms": 190.0,
        },
        "vehicle_continuity": {
            "passed": True,
            "plate_report": {
                "is_verified": True,
                "expected_plate": reg_num,
                "extracted_plate": reg_num,
                "ocr_confidence": 0.99,
                "duration_ms": 230.0,
            },
            "color_report": {
                "is_color_match": True,
                "expected_color_name": color,
                "measured_sat_median": 42.0,
                "measured_val_median": 160.0,
            },
            "cut_report": {
                "is_continuous": True,
                "evaluated_frames": 240,
                "cut_frame_indices": [],
            },
        },
        "dual_mask": {
            "passed": True,
            "grounded_parts": grounded_parts,
            "total_execution_ms": 510.0,
        },
        "vlm_inspection": {
            "passed": True,
            "forensic_integrity": {
                "rust_detected": False,
                "prior_putty_detected": False,
                "unrelated_prior_damage": False,
            },
            "verified_parts": verified_parts,
        },
    }

def _build_actuarial(make: str, model: str, year: int, reg_num: str, line_items: list[dict], gross: Decimal, initial: Decimal, target: Decimal, cap: Decimal):
    deductible = Decimal("1000.00")
    net = max(Decimal("0.00"), gross - deductible)
    gst = (net * Decimal("0.18")).quantize(Decimal("0.01"))
    return {
        "vehicle_make": make,
        "vehicle_model": model,
        "vehicle_year": year,
        "registration_number": reg_num,
        "pricing_model_version": "v2.1-prod",
        "summary": {
            "gross_garage_repair_inr": f"{gross:.2f}",
            "net_claim_liability_inr": f"{net:.2f}",
            "total_parts_cost_inr": f"{gross * Decimal('0.55'):.2f}",
            "total_labour_inr": f"{gross * Decimal('0.25'):.2f}",
            "total_paint_inr": f"{gross * Decimal('0.20'):.2f}",
            "compulsory_deductible_inr": f"{deductible:.2f}",
            "salvage_deduction_inr": "0.00",
            "gst_amount_inr": f"{gst:.2f}",
        },
        "settlement_band": {
            "initial_offer_inr": f"{initial:.2f}",
            "target_settlement_inr": f"{target:.2f}",
            "walkaway_cap_inr": f"{cap:.2f}",
            "financial_ceiling_inr": f"{cap * Decimal('1.5'):.2f}",
        },
        "line_items": line_items,
    }

def _build_negotiation(claim_id: uuid.UUID, policy_id: str, reg_num: str, vehicle_desc: str, initial_offer: Decimal, target: Decimal, cap: Decimal):
    expires_at = hmac_offer_signer.generate_expiration_epoch()
    sig = hmac_offer_signer.sign_offer(claim_id, round_num=0, amount_inr=initial_offer, expires_at_epoch=expires_at)
    card = OfferCardDTO(
        claim_id=claim_id,
        round_num=0,
        amount_inr=initial_offer,
        formatted_amount=f"₹{initial_offer:,.2f}",
        expires_at_epoch=expires_at,
        hmac_signature=sig,
    )
    turn = NegotiationTurnDTO(
        round_num=0,
        claimant_message="<INITIAL_OFFER>",
        parsed_counteroffer_inr=None,
        rationale_score=1.0,
        offered_amount_inr=initial_offer,
        chatbot_reply=(
            f"Namaste! Auto-Settle AI has completed algorithmic damage appraisal for your {vehicle_desc}. "
            f"Based on OEM parts schedules and zero-depreciation policy terms, our instant cash-in-lieu settlement "
            f"offer is {card.formatted_amount}. This offer is cryptographically locked and valid for 15 minutes."
        ),
        offer_card=card,
    )
    session = NegotiationSessionDTO(
        claim_id=claim_id,
        policy_id=policy_id,
        registration_number=reg_num,
        current_round=0,
        session_state=NegotiationRoundState.ROUND_0_INITIAL,
        settlement_band={
            "initial_offer_inr": f"{initial_offer:.2f}",
            "target_settlement_inr": f"{target:.2f}",
            "walkaway_cap_inr": f"{cap:.2f}",
            "financial_ceiling_inr": f"{cap * Decimal('1.5'):.2f}",
        },
        active_offer_card=card,
        turns=[turn],
    )
    return session.to_dict()

def _cache_keyframes_and_video(claim_id: uuid.UUID, video_rel_path: str):
    root = Path(__file__).resolve().parent.parent.parent.parent
    src_video = root / video_rel_path
    if not src_video.exists():
        logger.warning(f"Source video {src_video} not found for claim {claim_id}")
        return

    # 1. Copy video to claim storage
    raw_dir = Path("/tmp/autosettle_storage/claims") / str(claim_id) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest_video = raw_dir / "walkaround.mp4"
    shutil.copyfile(str(src_video), str(dest_video))

    # 2. Extract 5 evenly spaced keyframes
    kf_dir = Path("/tmp/autosettle_keyframes") / str(claim_id)
    kf_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(src_video))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames > 0:
        indices = [int(i * (total_frames - 1) / 4) for i in range(5)]
        for rank, fidx in enumerate(indices, start=1):
            cap.set(cv2.CAP_PROP_POS_FRAMES, fidx)
            ret, frame = cap.read()
            if ret:
                cv2.imwrite(str(kf_dir / f"keyframe_{rank:02d}.jpg"), frame)
    cap.release()

# ---------------------------------------------------------------------------
# Main Clear & Seed Engine
# ---------------------------------------------------------------------------
async def clear_and_seed_database(clear_existing: bool = True, include_demo_claims: bool = True) -> Dict[str, Any]:
    # 1. Ensure table schemas exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        if clear_existing:
            logger.info("Clearing claims, unrepaired ledger, OEM parts, and policies...")
            await session.execute(delete(Claim))
            await session.execute(delete(UnrepairedClaim))
            await session.execute(delete(OemPart))
            await session.execute(delete(InsuredPolicy))
            await session.commit()

        # 2. Seed Insured Policies
        policies = [
            # Video 1: car_002.mp4
            InsuredPolicy(
                policy_id="POL-HAPPY-001",
                policy_status="ACTIVE",
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=0,
                registration_number="MH12DE1433",
                vin_last_6="89412B",
                make="Hyundai",
                model="Creta",
                manufacturing_year=2023,
                registered_color="WHITE",
                registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 50, "v_min": 170, "v_max": 255},
                paint_type="metallic",
                zero_dep_addon=True,
                compulsory_deductible_inr=Decimal("1000.00"),
                estimated_ncb_loss_inr=Decimal("3200.00"),
            ),
            # Video 2: toyota-corolla-side-impact-damage-walkaround-houston.mp4
            InsuredPolicy(
                policy_id="POL-TOYOTA-008",
                policy_status="ACTIVE",
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=0,
                registration_number="TX-COROLLA-22",
                vin_last_6="COR22A",
                make="Toyota",
                model="Corolla",
                manufacturing_year=2022,
                registered_color="SILVER",
                registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 50, "v_min": 100, "v_max": 230},
                paint_type="metallic",
                zero_dep_addon=True,
                compulsory_deductible_inr=Decimal("1000.00"),
                estimated_ncb_loss_inr=Decimal("3500.00"),
            ),
            # Video 3: car_011.mp4 (Blue Hatchback / Tata Nexon)
            InsuredPolicy(
                policy_id="POL-BLUE-011",
                policy_status="ACTIVE",
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=0,
                registration_number="KA05MB1111",
                vin_last_6="NEX22B",
                make="Tata",
                model="Nexon",
                manufacturing_year=2022,
                registered_color="BLUE",
                registered_color_hsv={"h_min": 100, "h_max": 130, "s_min": 80, "s_max": 255, "v_min": 50, "v_max": 255},
                paint_type="metallic",
                zero_dep_addon=True,
                compulsory_deductible_inr=Decimal("1000.00"),
                estimated_ncb_loss_inr=Decimal("2800.00"),
            ),
            # Video 4: 10.mp4 (Toyota Camry XLE)
            InsuredPolicy(
                policy_id="POL-CAMRY-010",
                policy_status="ACTIVE",
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=0,
                registration_number="1673IK2",
                vin_last_6="CAM21C",
                make="Toyota",
                model="Camry",
                manufacturing_year=2021,
                registered_color="SILVER",
                registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 50, "v_min": 100, "v_max": 220},
                paint_type="metallic",
                zero_dep_addon=True,
                compulsory_deductible_inr=Decimal("1000.00"),
                estimated_ncb_loss_inr=Decimal("3800.00"),
            ),
            # Negative & Edge Cases
            InsuredPolicy(
                policy_id="POL-EXPIRED-002",
                policy_status="ACTIVE",
                policy_start_date=date(2024, 1, 1),
                policy_end_date=date(2024, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=0,
                registration_number="DL01AB9999",
                vin_last_6="12345A",
                make="Maruti",
                model="Swift",
                manufacturing_year=2021,
                registered_color="SILVER",
                registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 50, "v_min": 100, "v_max": 220},
                paint_type="metallic",
                zero_dep_addon=False,
                compulsory_deductible_inr=Decimal("1500.00"),
                estimated_ncb_loss_inr=Decimal("2500.00"),
            ),
            InsuredPolicy(
                policy_id="POL-FUTURE-003",
                policy_status="ACTIVE",
                policy_start_date=date(2027, 1, 1),
                policy_end_date=date(2027, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=0,
                registration_number="KA03MJ7777",
                vin_last_6="67890C",
                make="Kia",
                model="Seltos",
                manufacturing_year=2024,
                registered_color="BLACK",
                registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 255, "v_min": 0, "v_max": 50},
                paint_type="metallic",
                zero_dep_addon=True,
                compulsory_deductible_inr=Decimal("1000.00"),
                estimated_ncb_loss_inr=Decimal("3500.00"),
            ),
            InsuredPolicy(
                policy_id="POL-CLAIMCAP-004",
                policy_status="ACTIVE",
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=2,
                registration_number="MH14EU4321",
                vin_last_6="55443D",
                make="Tata",
                model="Nexon",
                manufacturing_year=2022,
                registered_color="BLUE",
                registered_color_hsv={"h_min": 100, "h_max": 130, "s_min": 80, "s_max": 255, "v_min": 50, "v_max": 255},
                paint_type="metallic",
                zero_dep_addon=True,
                compulsory_deductible_inr=Decimal("1000.00"),
                estimated_ncb_loss_inr=Decimal("2800.00"),
            ),
            InsuredPolicy(
                policy_id="POL-CANCELLED-005",
                policy_status="CANCELLED",
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=0,
                registration_number="MH02BQ1111",
                vin_last_6="99887E",
                make="Honda",
                model="City",
                manufacturing_year=2020,
                registered_color="WHITE",
                registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 45, "v_min": 180, "v_max": 255},
                paint_type="solid",
                zero_dep_addon=False,
                compulsory_deductible_inr=Decimal("2000.00"),
                estimated_ncb_loss_inr=Decimal("4000.00"),
            ),
            InsuredPolicy(
                policy_id="POL-RED-007",
                policy_status="ACTIVE",
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=0,
                registration_number="KA01MJ5555",
                vin_last_6="33221F",
                make="Hyundai",
                model="Creta",
                manufacturing_year=2023,
                registered_color="RED",
                registered_color_hsv={"h_min": 0, "h_max": 10, "s_min": 100, "s_max": 255, "v_min": 80, "v_max": 255},
                paint_type="metallic",
                zero_dep_addon=True,
                compulsory_deductible_inr=Decimal("1000.00"),
                estimated_ncb_loss_inr=Decimal("3200.00"),
            ),
        ]
        session.add_all(policies)

        # 3. Seed OEM Parts Catalogues (Generic Universal + Make/Model Specifics)
        oem_parts: list[OemPart] = []
        # Generic universal catalogue (fallback for any unknown make/model)
        oem_parts.extend(generate_scaled_parts("Generic", "Generic", "GEN-UNIV", 1.00))
        # Specific catalogues for the 4 demo vehicles + test vehicles
        oem_parts.extend(generate_scaled_parts("Hyundai", "Creta", "HYU-CRE", 1.00))
        oem_parts.extend(generate_scaled_parts("Toyota", "Corolla", "TOY-COR", 1.20))
        oem_parts.extend(generate_scaled_parts("Toyota", "Camry", "TOY-CAM", 1.35))
        oem_parts.extend(generate_scaled_parts("Tata", "Nexon", "TAT-NEX", 0.85))
        oem_parts.extend(generate_scaled_parts("Maruti", "Swift", "MAR-SWF", 0.72))
        session.add_all(oem_parts)

        if include_demo_claims:
            # 4. Seed Double-Dipping Prevention Ledger Record
            unrepaired = UnrepairedClaim(
                registration_number="MH12DE1433",
                canonical_part_key="back_bumper",
                damage_class="dent",
                settled_amount_inr=Decimal("4200.00"),
                is_repaired_verified=False,
            )
            session.add(unrepaired)

            # 5. Pre-stage Demo Claims for the 4 Authentic Test Videos

            # ---- CLAIM 1: car_002.mp4 (Hyundai Creta · Front Bumper & Door Dent) ----
            telemetry_c1 = _build_telemetry(
                "MH12DE1433", "WHITE",
                [
                    {"key": "front_bumper", "name": "Front Bumper Cover", "damage": "dent", "action": "REPAIR", "severity": "MODERATE", "reason": "Impact crease on front bumper lower valance"},
                    {"key": "front_left_light", "name": "Front Left Headlamp", "damage": "scratch", "action": "REPAIR", "severity": "MINOR", "reason": "Scuffed outer lens"},
                ]
            )
            actuarial_c1 = _build_actuarial(
                "Hyundai", "Creta", 2023, "MH12DE1433",
                [
                    {
                        "canonical_part_key": "front_bumper",
                        "display_part_name": "Front Bumper Cover",
                        "oem_part_number": "HYU-CRE-FRON",
                        "material": "plastic",
                        "action": "REPAIR",
                        "depth_grade": "L3_SHALLOW_DENT_PDR",
                        "iop_ratio": 0.14,
                        "base_part_cost_inr": "0.00",
                        "depreciation_rate_pct": "0.00",
                        "depreciation_amount_inr": "0.00",
                        "net_part_cost_inr": "0.00",
                        "salvage_deduction_inr": "0.00",
                        "rr_labour_inr": "850.00",
                        "denting_labour_inr": "1100.00",
                        "pdr_polish_flat_inr": "0.00",
                        "base_paint_inr": "3800.00",
                        "paint_multiplier": "1.00",
                        "paint_overlap_discount": "0.00",
                        "final_paint_inr": "3800.00",
                        "pre_tax_total_inr": "5750.00",
                        "gst_amount_inr": "1035.00",
                        "gross_line_item_total_inr": "6785.00",
                    },
                    {
                        "canonical_part_key": "front_left_light",
                        "display_part_name": "Front Left Headlamp",
                        "oem_part_number": "HYU-CRE-FRON",
                        "material": "assembly",
                        "action": "REPAIR",
                        "depth_grade": "L1_SURFACE_SCUFF",
                        "iop_ratio": 0.05,
                        "base_part_cost_inr": "0.00",
                        "depreciation_rate_pct": "0.00",
                        "depreciation_amount_inr": "0.00",
                        "net_part_cost_inr": "0.00",
                        "salvage_deduction_inr": "0.00",
                        "rr_labour_inr": "650.00",
                        "denting_labour_inr": "0.00",
                        "pdr_polish_flat_inr": "500.00",
                        "base_paint_inr": "0.00",
                        "paint_multiplier": "1.00",
                        "paint_overlap_discount": "0.00",
                        "final_paint_inr": "0.00",
                        "pre_tax_total_inr": "1150.00",
                        "gst_amount_inr": "207.00",
                        "gross_line_item_total_inr": "1357.00",
                    },
                ],
                gross=Decimal("11500.00"), initial=Decimal("8500.00"), target=Decimal("10000.00"), cap=Decimal("11500.00")
            )
            claim_1 = Claim(
                claim_id=CLAIM_CRETA_ID,
                policy_id="POL-HAPPY-001",
                video_sha256="demo_sha256_creta_car_002",
                capture_source="WEB_CLIENT_DEMO",
                is_demo_rehearsal=True,
                claim_description="Front bumper impact and scuff from parking pillar touch (car_002.mp4).",
                current_stage="STAGE_5_NEGOTIATION",
                claim_status="PRICED_READY_FOR_NEGOTIATION",
                escalation_code=None,
                failure_codes=None,
                fast_fail_telemetry=telemetry_c1["fast_fail"],
                vehicle_continuity_telemetry=telemetry_c1["vehicle_continuity"],
                dual_mask_telemetry=telemetry_c1["dual_mask"],
                vlm_inspection_telemetry=telemetry_c1["vlm_inspection"],
                actuarial_estimate=actuarial_c1,
                negotiation_session=_build_negotiation(CLAIM_CRETA_ID, "POL-HAPPY-001", "MH12DE1433", "Hyundai Creta", Decimal("8500.00"), Decimal("10000.00"), Decimal("11500.00")),
                settlement_voucher=None,
            )
            session.add(claim_1)

            # ---- CLAIM 2: toyota-corolla...mp4 (Toyota Corolla · Side Impact Dual Door Collision) ----
            telemetry_c2 = _build_telemetry(
                "TX-COROLLA-22", "SILVER",
                [
                    {"key": "front_left_door", "name": "Front Left Door Panel", "damage": "dent", "action": "REPAIR", "severity": "SEVERE", "reason": "Deep lateral crease from T-bone collision"},
                    {"key": "back_left_door", "name": "Rear Left Door Panel", "damage": "dent", "action": "REPAIR", "severity": "MODERATE", "reason": "Impact deformation along B-pillar"},
                ]
            )
            actuarial_c2 = _build_actuarial(
                "Toyota", "Corolla", 2022, "TX-COROLLA-22",
                [
                    {
                        "canonical_part_key": "front_left_door",
                        "display_part_name": "Front Left Door Panel",
                        "oem_part_number": "TOY-COR-FRON",
                        "material": "metal",
                        "action": "REPAIR",
                        "depth_grade": "L4_CREASED_DENT",
                        "iop_ratio": 0.28,
                        "base_part_cost_inr": "0.00",
                        "depreciation_rate_pct": "0.00",
                        "depreciation_amount_inr": "0.00",
                        "net_part_cost_inr": "0.00",
                        "salvage_deduction_inr": "0.00",
                        "rr_labour_inr": "1140.00",
                        "denting_labour_inr": "1680.00",
                        "pdr_polish_flat_inr": "0.00",
                        "base_paint_inr": "5040.00",
                        "paint_multiplier": "1.00",
                        "paint_overlap_discount": "0.00",
                        "final_paint_inr": "5040.00",
                        "pre_tax_total_inr": "7860.00",
                        "gst_amount_inr": "1414.80",
                        "gross_line_item_total_inr": "9274.80",
                    },
                    {
                        "canonical_part_key": "back_left_door",
                        "display_part_name": "Rear Left Door Panel",
                        "oem_part_number": "TOY-COR-BACK",
                        "material": "metal",
                        "action": "REPAIR",
                        "depth_grade": "L3_SHALLOW_DENT_PDR",
                        "iop_ratio": 0.18,
                        "base_part_cost_inr": "0.00",
                        "depreciation_rate_pct": "0.00",
                        "depreciation_amount_inr": "0.00",
                        "net_part_cost_inr": "0.00",
                        "salvage_deduction_inr": "0.00",
                        "rr_labour_inr": "1080.00",
                        "denting_labour_inr": "1620.00",
                        "pdr_polish_flat_inr": "0.00",
                        "base_paint_inr": "4800.00",
                        "paint_multiplier": "1.00",
                        "paint_overlap_discount": "0.00",
                        "final_paint_inr": "4800.00",
                        "pre_tax_total_inr": "7500.00",
                        "gst_amount_inr": "1350.00",
                        "gross_line_item_total_inr": "8850.00",
                    },
                ],
                gross=Decimal("19500.00"), initial=Decimal("16500.00"), target=Decimal("18500.00"), cap=Decimal("22000.00")
            )
            claim_2 = Claim(
                claim_id=CLAIM_COROLLA_ID,
                policy_id="POL-TOYOTA-008",
                video_sha256="demo_sha256_corolla_houston_side_impact",
                capture_source="WEB_CLIENT_DEMO",
                is_demo_rehearsal=True,
                claim_description="Side-impact collision with dual-door crease dents (Houston walkaround).",
                current_stage="STAGE_5_NEGOTIATION",
                claim_status="PRICED_READY_FOR_NEGOTIATION",
                escalation_code=None,
                failure_codes=None,
                fast_fail_telemetry=telemetry_c2["fast_fail"],
                vehicle_continuity_telemetry=telemetry_c2["vehicle_continuity"],
                dual_mask_telemetry=telemetry_c2["dual_mask"],
                vlm_inspection_telemetry=telemetry_c2["vlm_inspection"],
                actuarial_estimate=actuarial_c2,
                negotiation_session=_build_negotiation(CLAIM_COROLLA_ID, "POL-TOYOTA-008", "TX-COROLLA-22", "Toyota Corolla", Decimal("16500.00"), Decimal("18500.00"), Decimal("22000.00")),
                settlement_voucher=None,
            )
            session.add(claim_2)

            # ---- CLAIM 3: car_011.mp4 (Tata Nexon Blue · Settled PDR Cash-in-Lieu) ----
            telemetry_c3 = _build_telemetry(
                "KA05MB1111", "BLUE",
                [{"key": "front_right_door", "name": "Front Right Door", "damage": "dent", "action": "REPAIR", "severity": "MINOR", "reason": "Shallow door ding suitable for paintless dent repair"}]
            )
            actuarial_c3 = _build_actuarial(
                "Tata", "Nexon", 2022, "KA05MB1111",
                [
                    {
                        "canonical_part_key": "front_right_door",
                        "display_part_name": "Front Right Door",
                        "oem_part_number": "TAT-NEX-FRON",
                        "material": "metal",
                        "action": "REPAIR",
                        "depth_grade": "L3_SHALLOW_DENT_PDR",
                        "iop_ratio": 0.06,
                        "base_part_cost_inr": "0.00",
                        "depreciation_rate_pct": "0.00",
                        "depreciation_amount_inr": "0.00",
                        "net_part_cost_inr": "0.00",
                        "salvage_deduction_inr": "0.00",
                        "rr_labour_inr": "0.00",
                        "denting_labour_inr": "0.00",
                        "pdr_polish_flat_inr": "1200.00",
                        "base_paint_inr": "3200.00",
                        "paint_multiplier": "1.00",
                        "paint_overlap_discount": "0.00",
                        "final_paint_inr": "3200.00",
                        "pre_tax_total_inr": "4400.00",
                        "gst_amount_inr": "792.00",
                        "gross_line_item_total_inr": "5192.00",
                    }
                ],
                gross=Decimal("5192.00"), initial=Decimal("4000.00"), target=Decimal("4500.00"), cap=Decimal("5000.00")
            )
            voucher_c3 = voucher_generator.generate_voucher(
                claim_id=CLAIM_NEXON_ID,
                policy_id="POL-BLUE-011",
                registration_number="KA05MB1111",
                vehicle_make_model="Tata Nexon 2022",
                settled_amount_inr=Decimal("4500.00"),
                apportioned_parts=[
                    ApportionedPartPayoutDTO(
                        canonical_part_key="front_right_door",
                        display_part_name="Front Right Door",
                        damage_class="dent",
                        gross_line_item_inr=Decimal("5192.00"),
                        apportioned_amount_inr=Decimal("4500.00"),
                    ),
                ],
                beneficiary_upi_id="claimant.nexon@upi",
            )
            claim_3 = Claim(
                claim_id=CLAIM_NEXON_ID,
                policy_id="POL-BLUE-011",
                video_sha256="demo_sha256_nexon_car_011_pdr",
                capture_source="WEB_CLIENT_DEMO",
                is_demo_rehearsal=True,
                claim_description="Paintless Dent Repair (PDR) cash-in-lieu settled via UPI (car_011.mp4).",
                current_stage="STAGE_6_SETTLED",
                claim_status="SETTLED_CASH_IN_LIEU",
                escalation_code=None,
                failure_codes=None,
                fast_fail_telemetry=telemetry_c3["fast_fail"],
                vehicle_continuity_telemetry=telemetry_c3["vehicle_continuity"],
                dual_mask_telemetry=telemetry_c3["dual_mask"],
                vlm_inspection_telemetry=telemetry_c3["vlm_inspection"],
                actuarial_estimate=actuarial_c3,
                negotiation_session=_build_negotiation(CLAIM_NEXON_ID, "POL-BLUE-011", "KA05MB1111", "Tata Nexon", Decimal("4000.00"), Decimal("4500.00"), Decimal("5000.00")),
                settlement_voucher=voucher_c3.to_dict(),
            )
            session.add(claim_3)

            # ---- CLAIM 4: 10.mp4 (Toyota Camry XLE · Safety Critical Windshield Crack Escalated) ----
            telemetry_c4 = _build_telemetry(
                "1673IK2", "SILVER",
                [
                    {"key": "front_glass", "name": "Front Windshield", "damage": "glass_shatter", "action": "REPLACE", "severity": "CRITICAL", "reason": "Shattered laminated glass with spiderweb fracture pattern"},
                    {"key": "hood", "name": "Front Bonnet / Hood Panel", "damage": "dent", "action": "REPAIR", "severity": "MODERATE", "reason": "Front edge impact crumple"},
                ]
            )
            actuarial_c4 = _build_actuarial(
                "Toyota", "Camry", 2021, "1673IK2",
                [
                    {
                        "canonical_part_key": "front_glass",
                        "display_part_name": "Front Laminated Windshield",
                        "oem_part_number": "TOY-CAM-FRON",
                        "material": "glass",
                        "action": "REPLACE",
                        "depth_grade": "L5_STRUCTURAL_TEAR",
                        "iop_ratio": 0.40,
                        "base_part_cost_inr": "16740.00",
                        "depreciation_rate_pct": "0.00",
                        "depreciation_amount_inr": "0.00",
                        "net_part_cost_inr": "16740.00",
                        "salvage_deduction_inr": "0.00",
                        "rr_labour_inr": "2430.00",
                        "denting_labour_inr": "0.00",
                        "pdr_polish_flat_inr": "0.00",
                        "base_paint_inr": "0.00",
                        "paint_multiplier": "1.00",
                        "paint_overlap_discount": "0.00",
                        "final_paint_inr": "0.00",
                        "pre_tax_total_inr": "19170.00",
                        "gst_amount_inr": "3450.60",
                        "gross_line_item_total_inr": "22620.60",
                    }
                ],
                gross=Decimal("22620.60"), initial=Decimal("18000.00"), target=Decimal("20000.00"), cap=Decimal("25000.00")
            )
            dossier_c4 = dossier_builder.build_dossier(
                claim_id=CLAIM_CAMRY_ID,
                policy_id="POL-CAMRY-010",
                registration_number="1673IK2",
                escalation_code="ESC-06",
                forensic_telemetry=telemetry_c4,
                actuarial_summary=actuarial_c4["summary"],
                custom_reason="ESC-06: Safety-critical windshield fracture requires certified OEM replacement. Cash-in-lieu disallowed under IRDAI safety regulations.",
            )
            claim_4 = Claim(
                claim_id=CLAIM_CAMRY_ID,
                policy_id="POL-CAMRY-010",
                video_sha256="demo_sha256_camry_10_safety_crack",
                capture_source="WEB_CLIENT_DEMO",
                is_demo_rehearsal=True,
                claim_description="Shattered laminated windshield requiring physical surveyor inspection (10.mp4).",
                current_stage="STAGE_6_ESCALATION",
                claim_status="ESCALATED_HUMAN_SURVEYOR",
                escalation_code="ESC-06",
                failure_codes=["SAFETY_CRITICAL_COMPONENT_DAMAGED"],
                fast_fail_telemetry=telemetry_c4["fast_fail"],
                vehicle_continuity_telemetry=telemetry_c4["vehicle_continuity"],
                dual_mask_telemetry=telemetry_c4["dual_mask"],
                vlm_inspection_telemetry=telemetry_c4["vlm_inspection"],
                actuarial_estimate=actuarial_c4,
                negotiation_session=None,
                settlement_voucher=None,
            )
            session.add(claim_4)
            await session.commit()

            # 6. Pre-cache Keyframes and Videos to Storage
            _cache_keyframes_and_video(CLAIM_CRETA_ID, "test_assets/videos/car_002.mp4")
            _cache_keyframes_and_video(CLAIM_COROLLA_ID, "test_assets/videos/toyota-corolla-side-impact-damage-walkaround-houston.mp4")
            _cache_keyframes_and_video(CLAIM_NEXON_ID, "test_assets/videos/car_011.mp4")
            _cache_keyframes_and_video(CLAIM_CAMRY_ID, "test_assets/videos/10.mp4")
        else:
            await session.commit()
            for p in [Path("/tmp/autosettle_storage/claims"), Path("/tmp/autosettle_keyframes")]:
                if p.exists():
                    shutil.rmtree(str(p), ignore_errors=True)

        # 7. Clear Redis Claim Locks
        locks_cleared = await redis_manager.flush_locks()

    claims_count = 4 if include_demo_claims else 0
    result = {
        "status": "DATABASE_SEEDED_SUCCESS",
        "message": (
            "Cleared and seeded policies, Generic + OEM parts catalogues, and pre-staged claims for the 4 video test assets."
            if include_demo_claims
            else "Cleared all claim history and seeded policies + generic & OEM parts catalogue with clean slate for manual video upload testing."
        ),
        "counts": {
            "policies": len(policies),
            "oem_parts": len(oem_parts),
            "claims": claims_count,
            "locks_cleared": locks_cleared,
        },
        "demo_claims": [
            {
                "claim_id": str(CLAIM_CRETA_ID),
                "video": "car_002.mp4",
                "vehicle": "Hyundai Creta (2023)",
                "policy_id": "POL-HAPPY-001",
                "status": "PRICED_READY_FOR_NEGOTIATION",
                "stage": "STAGE_5_NEGOTIATION",
                "test_feature": "Interactive Bounded FSM Negotiation Chatbot & HMAC Acceptance",
                "url": f"http://127.0.0.1:3000/claims/{CLAIM_CRETA_ID}",
            },
            {
                "claim_id": str(CLAIM_COROLLA_ID),
                "video": "toyota-corolla-side-impact-damage-walkaround-houston.mp4",
                "vehicle": "Toyota Corolla (2022)",
                "policy_id": "POL-TOYOTA-008",
                "status": "PRICED_READY_FOR_NEGOTIATION",
                "stage": "STAGE_5_NEGOTIATION",
                "test_feature": "High-Impact Dual-Door Collision Damage & Actuarial Breakdown",
                "url": f"http://127.0.0.1:3000/claims/{CLAIM_COROLLA_ID}",
            },
            {
                "claim_id": str(CLAIM_NEXON_ID),
                "video": "car_011.mp4",
                "vehicle": "Tata Nexon (2022)",
                "policy_id": "POL-BLUE-011",
                "status": "SETTLED_CASH_IN_LIEU",
                "stage": "STAGE_6_SETTLED",
                "test_feature": "Settled Cash-in-Lieu Voucher, UPI Disbursement & PDF Download",
                "url": f"http://127.0.0.1:3000/claims/{CLAIM_NEXON_ID}",
            },
            {
                "claim_id": str(CLAIM_CAMRY_ID),
                "video": "10.mp4",
                "vehicle": "Toyota Camry XLE (2021)",
                "policy_id": "POL-CAMRY-010",
                "status": "ESCALATED_HUMAN_SURVEYOR",
                "stage": "STAGE_6_ESCALATION",
                "test_feature": "ESC-06 Safety-Critical Windshield Crack & Surveyor Adjuster Dossier",
                "url": f"http://127.0.0.1:3000/claims/{CLAIM_CAMRY_ID}",
            },
        ] if include_demo_claims else [],
    }
    logger.info(f"Seed complete: {result['counts']}")
    return result

async def seed_clean_slate() -> Dict[str, Any]:
    """Clears all claim history and seeds policies + parts so user/judges can upload videos fresh."""
    return await clear_and_seed_database(clear_existing=True, include_demo_claims=False)

async def seed_database() -> None:
    """Startup seed check: ensures policies and OEM parts exist without overwriting claims."""
    async with async_session_factory() as session:
        res = await session.execute(select(InsuredPolicy.policy_id).limit(1))
        if res.scalar_one_or_none():
            logger.info("Database policies and catalog already present.")
            return
    await clear_and_seed_database(clear_existing=False, include_demo_claims=False)

if __name__ == "__main__":
    asyncio.run(clear_and_seed_database(clear_existing=True, include_demo_claims=True))
