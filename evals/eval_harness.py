"""
evals/eval_harness.py
Interactive and CLI Evaluation Runner for Auto-Settle AI.

Usage Examples:
  # 1. Interactive terminal wizard:
  uv run python evals/eval_harness.py --interactive

  # 2. Direct run on any video with full pipeline:
  uv run python evals/eval_harness.py --video test_assets/videos/real_videos/toyota_hilux_white_ute.mp4 --claim "Scratched front bumper" --policy POL-HILUX-010

  # 3. Bypass Stage 0 & Stage 1 (e.g. video has cuts or low light, test Stage 2, 3, 4, 5, 6):
  uv run python evals/eval_harness.py --video test_assets/videos/car_videos/car_001.mp4 --claim "Scratched front bumper" --bypass stage_0,stage_1

  # 4. Interactive negotiation chat at Stage 5:
  uv run python evals/eval_harness.py --video test_assets/videos/car_videos/car_001.mp4 --claim "Scratched front bumper" --bypass stage_0,stage_1,stage_2 --interactive-chat

  # 5. Route to surveyor on rejection:
  uv run python evals/eval_harness.py --video test_assets/videos/car_videos/car_001.mp4 --claim "Scratched front bumper" --bypass stage_0,stage_1,stage_2 --strategy reject_to_surveyor
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evals.comprehensive_harness import (
    AuditTrail,
    ComprehensiveEvaluationHarness,
    ensure_test_policies,
)


# ==============================================================================
# TERMINAL UI FORMATTERS
# ==============================================================================

def print_header(title: str, width: int = 88) -> None:
    print("\n" + "=" * width)
    print(f"🚗 {title}".center(width))
    print("=" * width)


def print_stage_table(audit: AuditTrail) -> None:
    print("\n" + "-" * 88)
    print(f"{'STAGE':<30} | {'STATUS':<15} | {'LATENCY':<10} | {'REASON / SUMMARY'}")
    print("-" * 88)

    status_icons = {
        "PASSED": "✅ PASSED",
        "SETTLED_CASH": "💰 SETTLED",
        "ESCALATED_HUMAN": "📋 ESCALATED",
        "BYPASSED": "⚡ BYPASSED",
        "FAILED": "❌ FAILED",
        "ESCALATED": "⚠️ ESCALATED",
        "PENDING": "⏳ PENDING",
    }

    for stage_key, s in audit.stage_audits.items():
        st_display = status_icons.get(s.status, s.status)
        lat_display = f"{s.latency_ms:.1f}ms"
        reason = s.decision_reasoning or s.summary_message
        if len(reason) > 38:
            reason = reason[:35] + "..."
        print(f"{s.stage_name:<30} | {st_display:<15} | {lat_display:<10} | {reason}")

    print("-" * 88)
    print(f"⏱️  TOTAL LATENCY: {audit.total_execution_ms:.2f}ms | FINAL VERDICT: {audit.final_verdict}")
    print("-" * 88)


def print_perception_card(audit: AuditTrail) -> None:
    perc = getattr(audit, "perception_summary", None)
    if not perc:
        return

    print("\n" + "┌" + "─" * 86 + "┐")
    print(f"│ {'PERCEPTION: OCCLUSION-ROBUST RE-ID DAMAGE TRACKING TELEMETRY':^84} │")
    print("├" + "─" * 86 + "┤")
    print(f"│  Processed Frames:        {perc.get('total_frames_processed', 'N/A'):<58} │")
    print(f"│  Raw ByteTrack IDs:       {perc.get('raw_unique_ids', 'N/A'):<58} │")
    print(f"│  Re-ID Unique IDs:        {perc.get('reid_unique_ids', 'N/A'):<58} │")
    print(f"│  Confirmed Damage Tracks: {perc.get('confirmed_unique_ids', 'N/A'):<58} │")
    red = perc.get('id_switch_reduction_pct', 0.0)
    print(f"│  ID Switch Reduction:     {red:.2f}% (Suppressed {perc.get('raw_unique_ids', 0) - perc.get('reid_unique_ids', 0)} track fragmentations) │")
    classes = perc.get('confirmed_damage_classes', [])
    print(f"│  Confirmed Classes:       {', '.join(classes) if classes else 'None':<58} │")
    print("└" + "─" * 86 + "┘")


def print_damage_card(audit: AuditTrail) -> None:
    damages = getattr(audit, "damage_report", None) or []
    if not damages:
        return

    print("\n" + "┌" + "─" * 86 + "┐")
    print(f"│ {'STAGE 2 & 3 GROUNDED DAMAGE & VISUAL ANNOTATION REPORT':^84} │")
    print("├" + "─" * 86 + "┤")
    for idx, d in enumerate(damages, 1):
        pname = d.get("display_name", d.get("part_key", "Part"))
        onum = d.get("oem_number", "OEM-01")
        mat = d.get("material", "metal").upper()
        dmg_cls = d.get("damage_class", "damage").upper()
        depth = d.get("depth_grade", "VERIFIED")
        iop = d.get("iop_percentage", 0.0)
        rep = "REPAIR & PAINT" if d.get("is_repairable", True) else "REPLACE PART"

        print(f"│  [#{idx}] {pname.upper()} ({mat} | OEM: {onum}){' '*(56-len(pname)-len(mat)-len(onum))}│")
        print(f"│      Damage Type:  {dmg_cls:<20} | Depth: {depth:<25} │")
        print(f"│      Part Area IoP: {iop:.2f}%{' '*(19-len(f'{iop:.2f}'))} | Action: {rep:<24} │")

        full_img = d.get("full_annotated")
        som_img = d.get("som_crop")
        raw_img = d.get("raw_crop")

        if full_img:
            print(f"│      🖼️  Full Overlay : {full_img:<58} │")
        if som_img:
            print(f"│      🔍 SoM Crop     : {som_img:<58} │")
        if raw_img:
            print(f"│      📷 Raw Crop     : {raw_img:<58} │")
        if idx < len(damages):
            print("│" + " " * 86 + "│")

    print("├" + "─" * 86 + "┤")
    print("│  VEHICLE IMPACT FLANK SCHEMATIC:                                                    │")
    print("│       Front                                                     Rear                │")
    print("│     [ BUMPER ]──[ FRONT FENDER ]──[ FRONT DOOR * ]──[ REAR DOOR * ]──[ QUARTER ]    │")
    print("│                                       ^^^ DENT / SCRATCH IMPACT                     │")
    print("└" + "─" * 86 + "┘")


def print_financial_card(audit: AuditTrail) -> None:
    fin = audit.financial_summary
    if not fin:
        return

    print("\n" + "┌" + "─" * 86 + "┐")
    print(f"│ {'STATUTORY ACTUARIAL PRICING BREAKDOWN (IRDAI / OEM)':^84} │")
    print("├" + "─" * 86 + "┤")
    print(f"│  Gross Garage Repair Estimate:      ₹{fin.get('gross_repair_inr', '0.00'):<50} │")
    print(f"│  Less: Statutory Depreciation:      ₹{fin.get('total_depreciation_inr', '0.00'):<50} │")
    print(f"│  Net Insurer Claim Liability:       ₹{fin.get('net_liability_inr', '0.00'):<50} │")
    print(f"│  Cash Initial Offer (75%):          ₹{fin.get('initial_offer_inr', '0.00'):<50} │")
    print(f"│  Autonomous Ceiling Cap (95%):      ₹{fin.get('walkaway_cap_inr', '0.00'):<50} │")
    print(f"│  NCB Utility Recommendation:        {fin.get('ncb_recommendation', 'N/A'):<51} │")
    print("└" + "─" * 86 + "┘")


def print_artifacts_card(audit: AuditTrail) -> None:
    print("\n" + "┌" + "─" * 86 + "┐")
    print(f"│ {'GENERATED ARTIFACTS & AUDIT LOGS':^84} │")
    print("├" + "─" * 86 + "┤")
    for k, v in audit.generated_artifacts.items():
        if isinstance(v, list):
            print(f"│  {k:<24} : ({len(v)} files){' ' * 45} │")
            for item in v:
                short_item = str(item)
                if len(short_item) > 80:
                    short_item = "..." + short_item[-77:]
                print(f"│    • {short_item:<80} │")
        elif isinstance(v, dict):
            print(f"│  {k:<24} : ({len(v)} entries){' ' * 43} │")
        else:
            short_v = str(v)
            if len(short_v) > 57:
                short_v = "..." + short_v[-54:]
            print(f"│  {k:<24} : {short_v:<57} │")
    print("└" + "─" * 86 + "┘\n")


# ==============================================================================
# INTERACTIVE TERMINAL WIZARD
# ==============================================================================

async def run_interactive_wizard():
    print_header("AUTO-SETTLE AI — INTERACTIVE EVALUATION HARNESS")

    # 1. Discover available videos
    video_root = Path("test_assets/videos")
    available_videos = sorted(list(video_root.glob("**/*.mp4")))

    print("\n📁 Available Test Videos in Workspace:")
    for idx, v in enumerate(available_videos[:12], 1):
        rel = v.relative_to(PROJECT_ROOT)
        print(f"  [{idx:02d}] {rel}")

    print("  [00] Custom file path...")

    choice = input("\nSelect a video (number or custom path) [default: 01]: ").strip()
    selected_video: Path

    if not choice or choice == "1" or choice == "01":
        selected_video = available_videos[0]
    elif choice.isdigit() and 1 <= int(choice) <= len(available_videos):
        selected_video = available_videos[int(choice) - 1]
    else:
        custom_path = Path(choice)
        if not custom_path.exists():
            print(f"❌ File not found: {custom_path}. Using default: {available_videos[0]}")
            selected_video = available_videos[0]
        else:
            selected_video = custom_path

    print(f"Selected: {selected_video}")

    # 2. Claim description
    default_desc = "Scratched front bumper and dented front right door"
    desc_input = input(f"\nEnter claim description [default: '{default_desc}']: ").strip()
    claim_desc = desc_input if desc_input else default_desc

    # 3. Policy ID
    default_pol = "POL-HAPPY-001"
    pol_input = input(f"Enter policy ID [default: '{default_pol}']: ").strip()
    policy_id = pol_input if pol_input else default_pol

    # 4. Stage Bypasses
    print("\n⚡ Stage Bypassing Options (e.g. skip cuts, test downstream):")
    print("  [1] Run full end-to-end pipeline (no bypasses)")
    print("  [2] Bypass Stage 0 (Sanity/Quality Gate)")
    print("  [3] Bypass Stage 0 & Stage 1 (Extract keyframes directly, skip cuts)")
    print("  [4] Bypass Stage 0, 1, and 2 (Simulate detected front bumper damage)")
    print("  [5] Custom bypass selection")

    b_choice = input("Select bypass configuration [default: 3]: ").strip()
    bypass_stages: List[str] = []

    if b_choice == "1":
        bypass_stages = []
    elif b_choice == "2":
        bypass_stages = ["stage_0"]
    elif b_choice == "4":
        bypass_stages = ["stage_0", "stage_1", "stage_2"]
    elif b_choice == "5":
        raw_b = input("Enter stages to bypass (comma-separated, e.g. stage_0,stage_1): ").strip()
        bypass_stages = [x.strip() for x in raw_b.split(",") if x.strip()]
    else:  # default: 3
        bypass_stages = ["stage_0", "stage_1"]

    # 5. Negotiation mode
    print("\n🤝 Stage 5 Negotiation Strategy:")
    print("  [1] Counter-offer once, then accept cash settlement")
    print("  [2] Accept initial offer immediately")
    print("  [3] Reject cash offer (Escalate to Human Surveyor & Garage)")
    print("  [4] Interactive Chat (chat live in terminal with adjuster bot)")

    strat_choice = input("Select negotiation mode [default: 1]: ").strip()
    strat = "counter_then_accept"
    is_interactive_chat = False

    if strat_choice == "2":
        strat = "immediate_accept"
    elif strat_choice == "3":
        strat = "reject_to_surveyor"
    elif strat_choice == "4":
        strat = "interactive"
        is_interactive_chat = True

    # Interactive chat callback handler
    async def terminal_chat_handler(context: Dict[str, Any]) -> Dict[str, Any]:
        active_offer = context["active_offer"]
        amt = active_offer["amount_inr"]
        print(f"\n💬 [ADJUSTER BOT]: Initial Approved Cash Offer: ₹{Decimal(str(amt)):,.2f}")
        print("   Type: 'accept' to take the cash payout,")
        print("         'reject' to request physical garage repair,")
        print("         or type your counteroffer message (e.g. 'Can you do 9500?'):")
        user_msg = input("\nClaimant > ").strip()
        if user_msg.lower() == "accept":
            return {"action": "accept"}
        if user_msg.lower() == "reject":
            return {"action": "reject"}

        import re
        nums = re.findall(r"\d+", user_msg.replace(",", ""))
        counter_val = Decimal(nums[0]) if nums else Decimal(str(amt)) + Decimal("1000.00")
        return {"action": "counter", "message": user_msg, "counteroffer_inr": counter_val}

    print("\n🚀 Executing evaluation harness...\n")
    harness = ComprehensiveEvaluationHarness(vlm_provider="mock")

    async def sse_logger(event_name: str, payload: Dict[str, Any]):
        print(f"📡 [EVENT] {event_name:<30} | {str(payload)[:50]}...")

    audit = await harness.evaluate(
        media_path=selected_video,
        claim_description=claim_desc,
        policy_id=policy_id,
        bypass_stages=bypass_stages,
        overrides={"force_continue": True},
        negotiation_strategy=strat,
        interactive_negotiation_handler=terminal_chat_handler if is_interactive_chat else None,
        event_callback=sse_logger,
    )

    print_stage_table(audit)
    print_perception_card(audit)
    print_damage_card(audit)
    print_financial_card(audit)
    print_artifacts_card(audit)


# ==============================================================================
# CLI DISPATCHER
# ==============================================================================

async def main_cli():
    parser = argparse.ArgumentParser(description="Auto-Settle AI Master Evaluation Harness")
    parser.add_argument("--interactive", action="store_true", help="Launch interactive terminal wizard")
    parser.add_argument("--video", type=str, help="Path to input video file")
    parser.add_argument("--claim", type=str, default="Scratched front bumper", help="Natural language claim description")
    parser.add_argument("--policy", type=str, default="POL-HAPPY-001", help="Insured Policy ID")
    parser.add_argument("--bypass", type=str, default="", help="Comma-separated stages to bypass (e.g. stage_0,stage_1)")
    parser.add_argument("--strategy", type=str, default="counter_then_accept", choices=["counter_then_accept", "immediate_accept", "reject_to_surveyor", "interactive"])
    parser.add_argument("--vlm-provider", type=str, default="mock", choices=["mock", "auto", "gemini", "ollama"])
    parser.add_argument("--force-continue", action="store_true", help="Continue pipeline even if upstream stages escalate")
    parser.add_argument("--ignore-cuts", action="store_true", help="Bypass Stage 1 cut detection failure")
    parser.add_argument("--output-json", type=str, help="Path to save output audit trail JSON")

    args = parser.parse_args()

    if args.interactive or not args.video:
        await run_interactive_wizard()
        return

    v_path = Path(args.video)
    if not v_path.exists():
        print(f"❌ Error: Video file not found: {v_path}")
        sys.exit(1)

    bypass_list = [s.strip() for s in args.bypass.split(",") if s.strip()]

    policy_to_use = args.policy
    if policy_to_use == "POL-HAPPY-001" and "corolla" in v_path.name.lower():
        policy_to_use = "POL-COROLLA-013"

    print_header(f"EVALUATING: {v_path.name}")
    print(f"Claim: '{args.claim}' | Policy: {policy_to_use} | Bypassing: {bypass_list or 'None'}")

    harness = ComprehensiveEvaluationHarness(vlm_provider=args.vlm_provider)
    audit = await harness.evaluate(
        media_path=v_path,
        claim_description=args.claim,
        policy_id=policy_to_use,
        bypass_stages=bypass_list,
        overrides={"force_continue": args.force_continue, "ignore_cuts": args.ignore_cuts},
        negotiation_strategy=args.strategy,
    )

    print_stage_table(audit)
    print_perception_card(audit)
    print_damage_card(audit)
    print_financial_card(audit)
    print_artifacts_card(audit)

    if args.output_json:
        out_p = Path(args.output_json)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(audit.to_json(indent=2))
        print(f"💾 Full audit trail saved to: {out_p}")


if __name__ == "__main__":
    asyncio.run(main_cli())
