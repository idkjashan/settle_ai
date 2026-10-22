"""
scripts/seed_demo_settlement.py
Seeds realistic claims into PostgreSQL for interactive frontend testing:
1. PRICED_READY_FOR_NEGOTIATION (Claim ready for Stage 5 chat, counteroffers & HMAC acceptance)
2. SETTLED (Claim with generated Settlement Voucher, UPI disbursement, and PDF download)
3. ESCALATED (Claim with Surveyor Adjuster Dossier and PDF download)

Usage:
    python -m scripts.seed_demo_settlement
"""
import asyncio
from decimal import Decimal
import uuid
from datetime import datetime, timezone

from app.domain.negotiation_chatbot.hmac_signer import hmac_offer_signer
from app.domain.negotiation_chatbot.schemas import (
    NegotiationRoundState,
    NegotiationSessionDTO,
    NegotiationTurnDTO,
    OfferCardDTO,
)
from app.domain.settlement_escalation.schemas import (
    ApportionedPartPayoutDTO,
    SettlementVoucherDTO,
)
from app.domain.settlement_escalation.voucher_generator import voucher_generator
from app.domain.settlement_escalation.dossier_builder import dossier_builder
from app.infrastructure.db.models import Claim
from app.infrastructure.db.session import async_session_factory
from app.infrastructure.db.repositories import ClaimRepository
from sqlalchemy import select


CLAIM_NEGOTIATION_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
CLAIM_SETTLED_ID     = uuid.UUID("22222222-2222-4222-8222-222222222222")
CLAIM_ESCALATED_ID   = uuid.UUID("33333333-3333-4333-8333-333333333333")

POLICY_ID = "POL-HAPPY-001"
REGISTRATION_NUM = "MH12DE1433"


def build_actuarial_payload():
    return {
        "vehicle_make": "Hyundai",
        "vehicle_model": "Creta",
        "vehicle_year": 2023,
        "registration_number": REGISTRATION_NUM,
        "pricing_model_version": "v2.1-prod",
        "summary": {
            "gross_garage_repair_inr": "12800.00",
            "net_claim_liability_inr": "10800.00",
            "total_parts_cost_inr": "6000.00",
            "total_labour_inr": "2800.00",
            "total_paint_inr": "2000.00",
            "compulsory_deductible_inr": "1000.00",
            "salvage_deduction_inr": "0.00",
            "gst_amount_inr": "1944.00",
        },
        "settlement_band": {
            "initial_offer_inr": "8500.00",
            "target_settlement_inr": "10000.00",
            "walkaway_cap_inr": "11500.00",
            "financial_ceiling_inr": "25000.00",
        },
        "line_items": [
            {
                "canonical_part_key": "front_door_lh",
                "display_part_name": "Front Door (Driver Side)",
                "oem_part_number": "76003-M0000",
                "material": "steel",
                "action": "REPAIR",
                "depth_grade": "L2_CREASE_SHALLOW",
                "iop_ratio": 0.08,
                "base_part_cost_inr": "0.00",
                "depreciation_rate_pct": "0.00",
                "depreciation_amount_inr": "0.00",
                "net_part_cost_inr": "0.00",
                "salvage_deduction_inr": "0.00",
                "rr_labour_inr": "600.00",
                "denting_labour_inr": "1200.00",
                "pdr_polish_flat_inr": "0.00",
                "base_paint_inr": "2000.00",
                "paint_multiplier": "1.00",
                "paint_overlap_discount": "0.00",
                "final_paint_inr": "2000.00",
                "pre_tax_total_inr": "3800.00",
                "gst_amount_inr": "684.00",
                "gross_line_item_total_inr": "4484.00",
            },
            {
                "canonical_part_key": "front_bumper",
                "display_part_name": "Front Bumper Fascia",
                "oem_part_number": "86511-M0000",
                "material": "plastic",
                "action": "REPLACE",
                "depth_grade": "L3_SHALLOW_DENT_PDR",
                "iop_ratio": 0.12,
                "base_part_cost_inr": "6000.00",
                "depreciation_rate_pct": "0.00",
                "depreciation_amount_inr": "0.00",
                "net_part_cost_inr": "6000.00",
                "salvage_deduction_inr": "0.00",
                "rr_labour_inr": "500.00",
                "denting_labour_inr": "500.00",
                "pdr_polish_flat_inr": "0.00",
                "base_paint_inr": "0.00",
                "paint_multiplier": "1.00",
                "paint_overlap_discount": "0.00",
                "final_paint_inr": "0.00",
                "pre_tax_total_inr": "7000.00",
                "gst_amount_inr": "1260.00",
                "gross_line_item_total_inr": "8260.00",
            },
        ],
    }


def build_negotiation_session(claim_id: uuid.UUID, amount: Decimal = Decimal("8500.00")):
    expires_at = hmac_offer_signer.generate_expiration_epoch()
    sig = hmac_offer_signer.sign_offer(claim_id, round_num=0, amount_inr=amount, expires_at_epoch=expires_at)

    card = OfferCardDTO(
        claim_id=claim_id,
        round_num=0,
        amount_inr=amount,
        formatted_amount=f"₹{amount:,.2f}",
        expires_at_epoch=expires_at,
        hmac_signature=sig,
    )
    turn = NegotiationTurnDTO(
        round_num=0,
        claimant_message="<INITIAL_OFFER>",
        parsed_counteroffer_inr=None,
        rationale_score=1.0,
        offered_amount_inr=amount,
        chatbot_reply=(
            "Namaste! Auto-Settle AI has completed computer-vision damage appraisal for your Hyundai Creta. "
            "Based on OEM part rates and zero-depreciation policy coverage, our instant cash-in-lieu settlement "
            f"offer is {card.formatted_amount}. This offer is valid for 15 minutes."
        ),
        offer_card=card,
    )
    session = NegotiationSessionDTO(
        claim_id=claim_id,
        policy_id=POLICY_ID,
        registration_number=REGISTRATION_NUM,
        current_round=0,
        session_state=NegotiationRoundState.ROUND_0_INITIAL,
        settlement_band={
            "initial_offer_inr": "8500.00",
            "target_settlement_inr": "10000.00",
            "walkaway_cap_inr": "11500.00",
            "financial_ceiling_inr": "25000.00",
        },
        active_offer_card=card,
        turns=[turn],
    )
    return session.to_dict()


def build_sample_telemetry():
    return {
        "fast_fail": {
            "tier1_report": {
                "passed": True,
                "policy_id": POLICY_ID,
                "policy_status": "ACTIVE",
                "cash_claims_ytd": 0,
                "max_cash_claims_per_year": 2,
                "duration_ms": 11.4,
                "failure_codes": [],
            },
            "container_report": {
                "passed": True,
                "codec_name": "h264",
                "duration_sec": 6.0,
                "effective_fps": 30.0,
                "width": 1280,
                "height": 720,
            },
            "visual_report": {
                "passed": True,
                "mean_luminance_aggregate": 78.5,
                "mean_sharpness_aggregate": 890.2,
                "sampled_frames": [
                    {"frame_number": 0, "normalized_pos": 0.0, "mean_luminance_y": 78.0, "laplacian_variance": 900.0},
                    {"frame_number": 30, "normalized_pos": 0.2, "mean_luminance_y": 79.1, "laplacian_variance": 880.0},
                ],
            },
            "total_execution_ms": 185.0,
        },
        "vehicle_continuity": {
            "passed": True,
            "plate_report": {
                "is_verified": True,
                "expected_plate": REGISTRATION_NUM,
                "extracted_plate": REGISTRATION_NUM,
                "ocr_confidence": 0.994,
                "duration_ms": 240.0,
            },
            "color_report": {
                "is_color_match": True,
                "expected_color_name": "WHITE",
                "measured_sat_median": 45.0,
                "measured_val_median": 142.0,
            },
            "cut_report": {
                "is_continuous": True,
                "evaluated_frames": 180,
                "cut_frame_indices": [],
            },
        },
        "dual_mask": {
            "passed": True,
            "grounded_parts": [
                {
                    "canonical_part_key": "front_door_lh",
                    "display_part_name": "Front Door (Driver Side)",
                    "iou": 0.88,
                    "damage_type": "dent",
                    "damage_confidence": 0.94,
                },
                {
                    "canonical_part_key": "front_bumper",
                    "display_part_name": "Front Bumper Fascia",
                    "iou": 0.91,
                    "damage_type": "scratch",
                    "damage_confidence": 0.92,
                },
            ],
            "total_execution_ms": 520.0,
        },
        "vlm_inspection": {
            "passed": True,
            "forensic_integrity": {
                "rust_detected": False,
                "prior_putty_detected": False,
                "unrelated_prior_damage": False,
            },
            "verified_parts": [
                {
                    "part_name": "front_door_lh",
                    "damage_severity": "MODERATE",
                    "recommended_action": "REPAIR",
                    "confidence": 0.94,
                },
                {
                    "part_name": "front_bumper",
                    "damage_severity": "MINOR",
                    "recommended_action": "REPLACE",
                    "confidence": 0.92,
                },
            ],
        },
    }


async def seed_all():
    print("🌱 Connecting to PostgreSQL and seeding demo claims...")
    telemetry = build_sample_telemetry()
    actuarial = build_actuarial_payload()

    async with async_session_factory() as session:
        # Check / upsert CLAIM_NEGOTIATION_ID
        res = await session.execute(select(Claim).where(Claim.claim_id == CLAIM_NEGOTIATION_ID))
        existing_neg = res.scalar_one_or_none()
        if existing_neg:
            await session.delete(existing_neg)
            await session.flush()

        claim_neg = Claim(
            claim_id=CLAIM_NEGOTIATION_ID,
            policy_id=POLICY_ID,
            video_sha256="demo_sha256_negotiation_claim_1111",
            capture_source="WEB_CLIENT_DEMO",
            is_demo_rehearsal=True,
            claim_description="Front door crease dent & bumper scuff from pillar contact.",
            current_stage="STAGE_5_NEGOTIATION",
            claim_status="PRICED_READY_FOR_NEGOTIATION",
            escalation_code=None,
            failure_codes=None,
            fast_fail_telemetry=telemetry["fast_fail"],
            vehicle_continuity_telemetry=telemetry["vehicle_continuity"],
            dual_mask_telemetry=telemetry["dual_mask"],
            vlm_inspection_telemetry=telemetry["vlm_inspection"],
            actuarial_estimate=actuarial,
            negotiation_session=build_negotiation_session(CLAIM_NEGOTIATION_ID, Decimal("8500.00")),
            settlement_voucher=None,
        )
        session.add(claim_neg)

        # Check / upsert CLAIM_SETTLED_ID
        res_settled = await session.execute(select(Claim).where(Claim.claim_id == CLAIM_SETTLED_ID))
        existing_settled = res_settled.scalar_one_or_none()
        if existing_settled:
            await session.delete(existing_settled)
            await session.flush()

        voucher = voucher_generator.generate_voucher(
            claim_id=CLAIM_SETTLED_ID,
            policy_id=POLICY_ID,
            registration_number=REGISTRATION_NUM,
            vehicle_make_model="Hyundai Creta 2023",
            settled_amount_inr=Decimal("10000.00"),
            apportioned_parts=[
                ApportionedPartPayoutDTO(
                    canonical_part_key="front_door_lh",
                    display_part_name="Front Door (Driver Side)",
                    damage_class="dent",
                    gross_line_item_inr=Decimal("4484.00"),
                    apportioned_amount_inr=Decimal("3750.00"),
                ),
                ApportionedPartPayoutDTO(
                    canonical_part_key="front_bumper",
                    display_part_name="Front Bumper Fascia",
                    damage_class="scratch",
                    gross_line_item_inr=Decimal("8260.00"),
                    apportioned_amount_inr=Decimal("6250.00"),
                ),
            ],
            beneficiary_upi_id="claimant.demo@okaxis",
        )

        claim_settled = Claim(
            claim_id=CLAIM_SETTLED_ID,
            policy_id=POLICY_ID,
            video_sha256="demo_sha256_settled_claim_2222",
            capture_source="WEB_CLIENT_DEMO",
            is_demo_rehearsal=True,
            claim_description="Settled cash-in-lieu claim for Hyundai Creta front door repair.",
            current_stage="STAGE_6_SETTLED",
            claim_status="SETTLED_CASH_IN_LIEU",
            escalation_code=None,
            failure_codes=None,
            fast_fail_telemetry=telemetry["fast_fail"],
            vehicle_continuity_telemetry=telemetry["vehicle_continuity"],
            dual_mask_telemetry=telemetry["dual_mask"],
            vlm_inspection_telemetry=telemetry["vlm_inspection"],
            actuarial_estimate=actuarial,
            negotiation_session=build_negotiation_session(CLAIM_SETTLED_ID, Decimal("10000.00")),
            settlement_voucher=voucher.to_dict(),
        )
        session.add(claim_settled)

        # Check / upsert CLAIM_ESCALATED_ID
        res_esc = await session.execute(select(Claim).where(Claim.claim_id == CLAIM_ESCALATED_ID))
        existing_esc = res_esc.scalar_one_or_none()
        if existing_esc:
            await session.delete(existing_esc)
            await session.flush()

        dossier = dossier_builder.build_dossier(
            claim_id=CLAIM_ESCALATED_ID,
            policy_id=POLICY_ID,
            registration_number=REGISTRATION_NUM,
            escalation_code="ESC-06",
            forensic_telemetry=telemetry,
            actuarial_summary=actuarial["summary"],
            custom_reason="Windshield structural crack detected during video inspection.",
        )

        claim_esc = Claim(
            claim_id=CLAIM_ESCALATED_ID,
            policy_id=POLICY_ID,
            video_sha256="demo_sha256_escalated_claim_3333",
            capture_source="WEB_CLIENT_DEMO",
            is_demo_rehearsal=True,
            claim_description="Windshield crack requiring surveyor physical safety inspection.",
            current_stage="STAGE_6_ESCALATION",
            claim_status="ESCALATED_HUMAN_SURVEYOR",
            escalation_code="ESC-06",
            failure_codes=["SAFETY_CRITICAL_COMPONENT_DAMAGED"],
            fast_fail_telemetry=telemetry["fast_fail"],
            vehicle_continuity_telemetry=telemetry["vehicle_continuity"],
            dual_mask_telemetry=telemetry["dual_mask"],
            vlm_inspection_telemetry=telemetry["vlm_inspection"],
            actuarial_estimate=actuarial,
            negotiation_session=None,
            settlement_voucher=None,
        )
        session.add(claim_esc)

        await session.commit()

    print("✅ Seed completed successfully!")
    print(f"   1. Live Negotiation Claim: {CLAIM_NEGOTIATION_ID}")
    print(f"      Status: PRICED_READY_FOR_NEGOTIATION (Initial Offer: ₹8,500.00)")
    print(f"      URL: http://127.0.0.1:3000/claims/{CLAIM_NEGOTIATION_ID}")
    print(f"   2. Settled Voucher Claim:  {CLAIM_SETTLED_ID}")
    print(f"      Status: SETTLED_CASH_IN_LIEU (Settled: ₹10,000.00)")
    print(f"      URL: http://127.0.0.1:3000/claims/{CLAIM_SETTLED_ID}")
    print(f"   3. Escalated Claim:        {CLAIM_ESCALATED_ID}")
    print(f"      Status: ESCALATED_HUMAN_SURVEYOR (ESC-06 Windshield)")
    print(f"      URL: http://127.0.0.1:3000/claims/{CLAIM_ESCALATED_ID}")


if __name__ == "__main__":
    asyncio.run(seed_all())

