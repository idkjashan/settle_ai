"""
scripts/seed_toyota_corolla.py
Seeds:
1. InsuredPolicy: POL-TOYOTA-008 (Toyota Corolla 2022, Silver, Active)
2. OEM Parts: 22 canonical parts for Toyota Corolla in oem_parts_catalogue
3. Video: Copies toyota-corolla-side-impact-damage-walkaround-houston.mp4 to persistent storage
4. Claim: 44444444-4444-4444-4444-444444444444 with dual-door damage (front left door + back left door),
          actuarial repair calculation, and active negotiation session.
"""

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import shutil
import uuid

from sqlalchemy import select
from app.infrastructure.db.session import async_session_factory
from app.infrastructure.db.models import InsuredPolicy, OemPart, Claim
from app.infrastructure.db.seed import HYUNDAI_CRETA_PARTS, generate_scaled_parts
from app.domain.negotiation_chatbot.hmac_signer import hmac_offer_signer
from app.domain.negotiation_chatbot.schemas import (
    OfferCardDTO,
    NegotiationRoundState,
    NegotiationTurnDTO,
    NegotiationSessionDTO,
)

TOYOTA_POLICY_ID = "POL-TOYOTA-008"
TOYOTA_CLAIM_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
REG_NUMBER = "TX-COROLLA-22"


async def seed_toyota_corolla():
    async with async_session_factory() as session:
        # 1. Upsert Policy
        policy = await session.get(InsuredPolicy, TOYOTA_POLICY_ID)
        if not policy:
            policy = InsuredPolicy(
                policy_id=TOYOTA_POLICY_ID,
                policy_status="ACTIVE",
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=0,
                registration_number=REG_NUMBER,
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
            )
            session.add(policy)
            print(f"Created policy {TOYOTA_POLICY_ID} for Toyota Corolla.")
        else:
            print(f"Policy {TOYOTA_POLICY_ID} already exists.")

        # 2. Seed OEM Parts for Toyota Corolla
        stmt = select(OemPart).where(OemPart.make == "Toyota", OemPart.model == "Corolla")
        res = await session.execute(stmt)
        existing_parts = res.scalars().all()
        if not existing_parts:
            toyota_parts = generate_scaled_parts(
                make="Toyota",
                model="Corolla",
                part_num_prefix="67001-COR",
                multiplier=1.20,
            )
            session.add_all(toyota_parts)
            print(f"Seeded {len(toyota_parts)} OEM parts for Toyota Corolla.")
        else:
            print(f"Toyota Corolla already has {len(existing_parts)} OEM parts in database.")

        await session.commit()

        # 3. Copy Video to Storage
        video_src = Path("test_assets/videos/simple/toyota-corolla-side-impact-damage-walkaround-houston.mp4")
        claim_storage_dir = Path("/tmp/autosettle_storage/claims") / str(TOYOTA_CLAIM_ID) / "raw"
        claim_storage_dir.mkdir(parents=True, exist_ok=True)
        dest_video = claim_storage_dir / "walkaround.mp4"
        if video_src.exists():
            shutil.copyfile(str(video_src), str(dest_video))
            print(f"Copied walkaround video to {dest_video}")
        else:
            print(f"Source video {video_src} not found, skipping video copy.")

        # Also extract sample keyframes for this claim
        kf_dir = Path("/tmp/autosettle_keyframes") / str(TOYOTA_CLAIM_ID)
        kf_dir.mkdir(parents=True, exist_ok=True)
        if dest_video.exists():
            import cv2
            cap = cv2.VideoCapture(str(dest_video))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames > 0:
                for idx, r in enumerate([0.1, 0.3, 0.5, 0.7, 0.9], 1):
                    f_no = min(int(total_frames * r), total_frames - 1)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, f_no)
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        out_p = kf_dir / f"keyframe_{idx:02d}.jpg"
                        cv2.imwrite(str(out_p), frame)
            cap.release()
            print(f"Extracted 5 keyframes to {kf_dir}")

        # 4. Build Telemetry & Actuarial Pricing for Toyota Corolla Front & Back Door Damage
        now_iso = datetime.now(timezone.utc).isoformat()
        
        telemetry_fast_fail = {
            "tier1_report": {
                "passed": True,
                "policy_id": TOYOTA_POLICY_ID,
                "sha256_hex": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "duration_ms": 11.2,
                "failure_codes": [],
                "policy_status": "ACTIVE",
                "cash_claims_ytd": 0,
                "max_cash_claims_per_year": 2,
            },
            "container_report": {
                "passed": True,
                "format_name": "mov,mp4",
                "width": 1080,
                "height": 1920,
                "duration_sec": 35.5,
                "effective_fps": 30.0,
                "codec_name": "h264",
                "duration_source": "format",
                "detected_editor_tag": None,
                "duration_ms": 18.4,
                "failure_codes": [],
            },
            "visual_report": {
                "passed": True,
                "mean_luminance_aggregate": 88.5,
                "mean_sharpness_aggregate": 642.0,
                "dark_frame_count": 0,
                "blurry_frame_count": 0,
                "bright_frame_count": 0,
                "sampled_frames": [],
                "failure_codes": [],
                "duration_ms": 115.0,
            },
            "capture_modality": "VIDEO_WALKAROUND",
            "total_execution_ms": 154.2,
        }

        telemetry_continuity = {
            "passed": True,
            "escalation_code": None,
            "total_execution_ms": 2840.0,
            "cut_report": {
                "is_continuous": True,
                "evaluated_frames": 1065,
                "cut_frame_indices": [],
                "min_triggered_ssim": 0.94,
                "min_global_hsv_corr": 0.92,
                "max_pyscenedetect_score": 14.2,
                "duration_ms": 850.0,
                "effective_fps": 30.0,
                "failure_code": None,
            },
            "plate_report": {
                "is_verified": True,
                "extracted_plate": REG_NUMBER,
                "expected_plate": REG_NUMBER,
                "ocr_confidence": 0.985,
                "homoglyph_edit_cost": 0.0,
                "anchor_frame_idx": 15,
                "is_spatially_grounded_on_vehicle": True,
                "duration_ms": 1420.0,
                "failure_code": None,
            },
            "color_report": {
                "is_color_match": True,
                "expected_color_name": "SILVER",
                "measured_hue_circular_mean": 95.0,
                "measured_sat_median": 28.0,
                "measured_val_median": 185.0,
                "delta_e_hsv": 0.0,
                "valid_paint_pixel_count": 142500,
                "duration_ms": 12.0,
                "failure_code": None,
            },
            "tracking_report": {
                "is_persistent": True,
                "frames_tracked": 1065,
                "target_track_id": 1,
                "track_lost_count": 0,
                "curated_keyframes": [str(kf_dir / f"keyframe_{i:02d}.jpg") for i in range(1, 6)],
                "saved_keyframes": {
                    "front_bumper": str(kf_dir / "keyframe_01.jpg"),
                    "side_body_panel": str(kf_dir / "keyframe_02.jpg"),
                    "damage_closeup_primary": str(kf_dir / "keyframe_03.jpg"),
                },
                "duration_ms": 1200.0,
                "failure_code": None,
            },
        }

        telemetry_dual_mask = {
            "schema_version": "2.0.0",
            "stage_passed": True,
            "escalation_code": None,
            "failure_codes": [],
            "grounded_parts": [
                {
                    "canonical_part_key": "front_left_door",
                    "display_part_name": "Front Left Door Panel",
                    "detected_damages": ["dent", "scratch"],
                    "primary_damage_type": "dent",
                    "iop_percentage": 42.5,
                    "confidence": 0.94,
                    "is_claimed": True,
                    "claim_status": "CLAIMED",
                    "bbox": [180, 240, 720, 950],
                    "segmentation_area_px": 84200,
                },
                {
                    "canonical_part_key": "back_left_door",
                    "display_part_name": "Rear Left Door Panel",
                    "detected_damages": ["dent", "scratch"],
                    "primary_damage_type": "dent",
                    "iop_percentage": 38.0,
                    "confidence": 0.91,
                    "is_claimed": True,
                    "claim_status": "CLAIMED",
                    "bbox": [650, 260, 1150, 960],
                    "segmentation_area_px": 76800,
                },
            ],
            "discarded_spillover_hits": [],
            "unclaimed_candidates": [],
            "unclaimed_preexisting_damage_detected": False,
            "latency_ms": {
                "dual_gpu_infer_ms": 420.0,
                "shapely_and_grouping_ms": 14.5,
                "total_ms": 435.0,
            },
        }

        telemetry_vlm = {
            "schema_version": "2.0.0",
            "provider": "ollama",
            "model_version": "minicpm-v:8b",
            "latency_ms": 3200.0,
            "verified_parts": [
                {
                    "canonical_part_key": "front_left_door",
                    "display_part_name": "Front Left Door Panel",
                    "damage_type": "dent",
                    "damage_confidence": 0.95,
                    "depth_grade": "D4",
                    "severity": "L4",
                    "repair_action": "REPAIR",
                    "preexisting": False,
                    "visual_reasoning_short": "Deep longitudinal crease across front left door skin with clear paint fracture. Fresh deformation without oxidation or primer chalking.",
                    "iop_percentage": 42.5,
                    "vlm_confidence": 0.94,
                },
                {
                    "canonical_part_key": "back_left_door",
                    "display_part_name": "Rear Left Door Panel",
                    "damage_type": "dent",
                    "damage_confidence": 0.92,
                    "depth_grade": "D4",
                    "severity": "L4",
                    "repair_action": "REPAIR",
                    "preexisting": False,
                    "visual_reasoning_short": "Contiguous impact dent spreading across the front edge of the rear left door panel. Surface clearcoat abraded.",
                    "iop_percentage": 38.0,
                    "vlm_confidence": 0.91,
                },
            ],
            "quarantined_parts": [],
            "escalation_flags": [],
        }

        actuarial_estimate = {
            "vehicle_make": "Toyota",
            "vehicle_model": "Corolla",
            "vehicle_year": 2022,
            "registration_number": REG_NUMBER,
            "pricing_model_version": "v2.1-prod",
            "summary": {
                "gross_garage_repair_inr": "18800.00",
                "net_claim_liability_inr": "15800.00",
                "total_parts_cost_inr": "0.00",
                "total_labour_inr": "6800.00",
                "total_paint_inr": "9400.00",
                "compulsory_deductible_inr": "1000.00",
                "salvage_deduction_inr": "0.00",
                "gst_amount_inr": "2916.00",
            },
            "settlement_band": {
                "target_offer_inr": "14200.00",
                "min_band_inr": "12800.00",
                "max_band_inr": "15600.00",
                "instant_payout_discount_pct": 20.0,
            },
            "line_items": [
                {
                    "canonical_part_key": "front_left_door",
                    "display_part_name": "Front Left Door Panel",
                    "oem_part_number": "67001-COR-01",
                    "material": "metal",
                    "depth_grade": "D4",
                    "repair_action": "REPAIR",
                    "part_cost_inr": "0.00",
                    "rr_labour_inr": "1440.00",
                    "denting_labour_inr": "2160.00",
                    "paint_inr": "4800.00",
                    "subtotal_inr": "8400.00",
                },
                {
                    "canonical_part_key": "back_left_door",
                    "display_part_name": "Rear Left Door Panel",
                    "oem_part_number": "67003-COR-01",
                    "material": "metal",
                    "depth_grade": "D4",
                    "repair_action": "REPAIR",
                    "part_cost_inr": "0.00",
                    "rr_labour_inr": "1320.00",
                    "denting_labour_inr": "2040.00",
                    "paint_inr": "4600.00",
                    "subtotal_inr": "7960.00",
                },
            ],
        }

        # 5. Create HMAC Signed Offer Card
        import time
        offer_amount = Decimal("14200.00")
        expires_at = int(time.time()) + 86400 * 3
        sig = hmac_offer_signer.sign_offer(
            TOYOTA_CLAIM_ID,
            round_num=0,
            amount_inr=offer_amount,
            expires_at_epoch=expires_at,
        )

        initial_offer_card = OfferCardDTO(
            claim_id=TOYOTA_CLAIM_ID,
            round_num=0,
            amount_inr=offer_amount,
            formatted_amount=f"₹{offer_amount:,.2f}",
            expires_at_epoch=expires_at,
            hmac_signature=sig,
        )

        turn = NegotiationTurnDTO(
            round_num=0,
            claimant_message="<INITIAL_OFFER>",
            parsed_counteroffer_inr=None,
            rationale_score=1.0,
            offered_amount_inr=offer_amount,
            chatbot_reply=(
                "Namaste! Auto-Settle AI has completed computer-vision appraisal for your Toyota Corolla. "
                "Dual-door denting and refinishing repairs have been approved for ₹14,200 instant cash settlement."
            ),
            offer_card=initial_offer_card,
        )

        negotiation_session = NegotiationSessionDTO(
            claim_id=TOYOTA_CLAIM_ID,
            policy_id=TOYOTA_POLICY_ID,
            registration_number=REG_NUMBER,
            current_round=0,
            session_state=NegotiationRoundState.ROUND_0_INITIAL,
            settlement_band={
                "initial_offer_inr": "12800.00",
                "target_settlement_inr": "14200.00",
                "walkaway_cap_inr": "15600.00",
                "financial_ceiling_inr": "18800.00",
            },
            active_offer_card=initial_offer_card,
            turns=[turn],
        )

        # 6. Upsert the Claim Record
        claim = await session.get(Claim, TOYOTA_CLAIM_ID)
        if not claim:
            claim = Claim(
                claim_id=TOYOTA_CLAIM_ID,
                policy_id=TOYOTA_POLICY_ID,
                video_sha256="toyota_corolla_houston_walkaround_sha256",
                capture_source="FILE_UPLOAD",
                is_demo_rehearsal=True,
                claim_description="Severe side impact dent across front left door and back left door from side-swipe.",
                raw_video_s3_key=f"claims/{TOYOTA_CLAIM_ID}/raw/walkaround.mp4",
                current_stage="STAGE_5_NEGOTIATION",
                claim_status="PRICED_READY_FOR_NEGOTIATION",
                escalation_code=None,
                failure_codes=[],
                fast_fail_telemetry=telemetry_fast_fail,
                vehicle_continuity_telemetry=telemetry_continuity,
                dual_mask_telemetry=telemetry_dual_mask,
                vlm_inspection_telemetry=telemetry_vlm,
                actuarial_estimate=actuarial_estimate,
                negotiation_session=negotiation_session.to_dict(),
                settlement_voucher=None,
            )
            session.add(claim)
            print(f"Created Toyota Corolla Claim {TOYOTA_CLAIM_ID} in PRICED_READY_FOR_NEGOTIATION.")
        else:
            claim.policy_id = TOYOTA_POLICY_ID
            claim.current_stage = "STAGE_5_NEGOTIATION"
            claim.claim_status = "PRICED_READY_FOR_NEGOTIATION"
            claim.fast_fail_telemetry = telemetry_fast_fail
            claim.vehicle_continuity_telemetry = telemetry_continuity
            claim.dual_mask_telemetry = telemetry_dual_mask
            claim.vlm_inspection_telemetry = telemetry_vlm
            claim.actuarial_estimate = actuarial_estimate
            claim.negotiation_session = negotiation_session.to_dict()
            print(f"Updated Toyota Corolla Claim {TOYOTA_CLAIM_ID}.")

        await session.commit()
        print("Successfully seeded Toyota Corolla policy, OEM parts, and ready-to-test claim!")


if __name__ == "__main__":
    asyncio.run(seed_toyota_corolla())
