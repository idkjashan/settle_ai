#!/usr/bin/env python3
"""
E2E integration test for all 4 benchmark videos.
Simulates frontend POST /api/v1/claims/upload for each preset,
streams SSE events from /api/v1/claims/{id}/events, and validates outcomes.
"""
import asyncio
import json
import sys
import time
import httpx
from pathlib import Path

BASE = "http://localhost:8000"
VIDEO_DIR = Path(__file__).parent.parent / "test_assets/videos/simple"

VIDEOS = [
    {
        "name": "Hyundai Creta (car_002.mp4)",
        "file": "car_002.mp4",
        "policy_id": "POL-HAPPY-001",
        "description": "front bumper crack and headlamp scuff",
        "expect_pass": True,
        "expect_esc": None,
    },
    {
        "name": "Toyota Corolla (side impact)",
        "file": "toyota-corolla-side-impact-damage-walkaround-houston.mp4",
        "policy_id": "POL-TOYOTA-008",
        "description": "side collision front door and back door dent",
        "expect_pass": True,
        "expect_esc": None,
    },
    {
        "name": "Tata Nexon (car_011.mp4)",
        "file": "car_011.mp4",
        "policy_id": "POL-BLUE-011",
        "description": "front right door dent",
        "expect_pass": True,
        "expect_esc": None,
    },
    {
        "name": "Toyota Camry (10.mp4) — ESC-06 expected",
        "file": "10.mp4",
        "policy_id": "POL-CAMRY-010",
        "description": "front glass shattered windshield",
        "expect_pass": False,
        "expect_esc": "ESC-06",
    },
]


def print_banner(text: str):
    bar = "=" * 70
    print(f"\n{bar}\n  {text}\n{bar}")


async def upload_and_stream(video: dict, timeout_s: int = 300) -> dict:
    """Upload video and consume SSE stream; return result summary."""
    vpath = VIDEO_DIR / video["file"]
    if not vpath.exists():
        return {"status": "SKIP", "reason": f"File not found: {vpath}", "verdict": "SKIP"}

    print_banner(f"Testing: {video['name']}")
    print(f"  Policy  : {video['policy_id']}")
    print(f"  Desc    : {video['description']}")
    print(f"  File    : {vpath} ({vpath.stat().st_size // 1024} KB)")

    # ── Upload ────────────────────────────────────────────────────────────
    t0 = time.time()
    async with httpx.AsyncClient(timeout=60.0) as client:
        with open(vpath, "rb") as fh:
            upload_resp = await client.post(
                f"{BASE}/api/v1/claims/upload",
                data={
                    "policy_id": video["policy_id"],
                    "claim_description": video["description"],
                    "is_demo_rehearsal": "true",
                    "skip_stage_0": "true",
                    "skip_stage_1": "true",
                },
                files={"video_file": (video["file"], fh, "video/mp4")},
            )

    # 202 = accepted (fast-fail passed, background task queued)
    # 200 = rejected (fast-fail failed with ESC-00)
    # 409 = lock conflict (same video already in flight)
    if upload_resp.status_code not in (200, 202):
        print(f"  ❌ UPLOAD FAILED: HTTP {upload_resp.status_code}")
        print(f"     Body: {upload_resp.text[:500]}")
        return {"name": video["name"], "status": "UPLOAD_FAIL",
                "http": upload_resp.status_code, "verdict": "FAIL"}

    claim_data = upload_resp.json()
    passed = claim_data.get("passed", True)
    claim_id = claim_data.get("claim_id")
    # Use the SSE URL from the response if available, else default
    sse_path = claim_data.get("sse_stream_url") or f"/api/v1/claims/{claim_id}/events"

    if not passed:
        esc = claim_data.get("escalation_code", "ESC-00")
        print(f"  ⚠️  Fast-fail rejected: esc={esc} — claim_id={claim_id}")
        result = {
            "name": video["name"], "claim_id": claim_id, "esc_code": esc,
            "elapsed_s": round(time.time() - t0, 1), "db_esc": esc,
        }
        passed_verdict = _check_pass(video, result)
        result["verdict"] = "PASS" if passed_verdict else "FAIL"
        print(f"  VERDICT: {'✅ PASS' if passed_verdict else '❌ FAIL'}")
        return result

    print(f"  ✅ Upload {upload_resp.status_code} → claim_id={claim_id}  ({time.time()-t0:.1f}s)")

    # ── Poll DB for completion (the SSE stream may have events already published) ──
    # Also stream SSE to capture real-time events
    events = []
    final_status = None
    esc_code = None
    stage_reached = None
    timeout_hit = False
    sse_url = f"{BASE}{sse_path}"
    print(f"  → Streaming SSE from {sse_url} ...")
    print(f"  {'EVENT':<45} {'STAGE':<30}")
    print(f"  {'-'*45} {'-'*30}")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s + 10.0, connect=10.0)
        ) as client:
            async with client.stream("GET", sse_url) as resp:
                if resp.status_code != 200:
                    print(f"  ⚠️  SSE endpoint returned HTTP {resp.status_code}")
                else:
                    deadline = time.time() + timeout_s
                    async for raw_line in resp.aiter_lines():
                        if time.time() > deadline:
                            timeout_hit = True
                            break
                        if not raw_line.startswith("data:"):
                            continue
                        payload_str = raw_line[5:].strip()
                        if not payload_str:
                            continue
                        try:
                            payload = json.loads(payload_str)
                        except json.JSONDecodeError:
                            continue

                        event_type = (
                            payload.get("event") or
                            payload.get("type") or
                            payload.get("status", "")
                        )
                        stage = payload.get("stage") or payload.get("current_stage", "")
                        events.append(event_type)
                        print(f"  {event_type:<45} {str(stage):<30}")

                        # Track final state
                        esc_in_payload = payload.get("escalation_code") or payload.get("code", "")
                        if esc_in_payload:
                            esc_code = esc_in_payload
                        if "ESC-06" in str(payload):
                            esc_code = "ESC-06"
                        if stage:
                            stage_reached = stage

                        terminal_keywords = [
                            "COMPLETE", "PRICED", "ESCALAT", "DONE", "SETTLED",
                            "CLAIM_OFFER_READY", "STAGE_4_PRICING_COMPLETED",
                            "ACTUARIAL_PRICING_COMPLETED", "SAFETY_CRITICAL",
                            "STAGE_2_FAILED", "STAGE_3_FAILED", "STAGE_4_FAILED",
                            "STAGE_1_FAILED", "STAGE_5_INITIALIZED",
                        ]
                        if any(k in event_type.upper() for k in terminal_keywords):
                            final_status = event_type
                            break
    except httpx.ReadTimeout:
        timeout_hit = True
        final_status = "SSE_TIMEOUT"
    except Exception as sse_err:
        print(f"  ⚠️  SSE stream error: {sse_err}")

    elapsed = time.time() - t0
    result = {
        "name": video["name"],
        "claim_id": claim_id,
        "events": events,
        "stage_reached": stage_reached,
        "final_status": final_status or "UNKNOWN",
        "esc_code": esc_code,
        "elapsed_s": round(elapsed, 1),
        "timeout": timeout_hit,
    }

    # ── Fetch final DB state ───────────────────────────────────────────────
    async with httpx.AsyncClient(timeout=30.0) as client:
        db_resp = await client.get(f"{BASE}/api/v1/claims/{claim_id}")
    if db_resp.status_code == 200:
        db = db_resp.json()
        result["db_status"] = db.get("claim_status")
        result["db_stage"] = db.get("current_stage")
        result["db_esc"] = db.get("escalation_code")
        t = db.get("telemetry", {}) or {}
        result["has_actuarial"] = bool(t.get("actuarial_estimate"))
        result["has_negotiation"] = bool(t.get("negotiation_session"))
        result["has_settlement"] = bool(t.get("settlement_voucher"))
        dm = t.get("dual_mask")
        if dm:
            result["grounded_parts_count"] = len((dm or {}).get("grounded_parts", []))

    # ── Verdict ────────────────────────────────────────────────────────────
    print(f"\n  ┌─ RESULT ─────────────────────────────────────────────")
    print(f"  │ claim_id       : {claim_id}")
    print(f"  │ stage          : {result.get('db_stage', stage_reached)}")
    print(f"  │ status         : {result.get('db_status', final_status)}")
    print(f"  │ esc_code       : {result.get('db_esc', esc_code)}")
    print(f"  │ grounded_parts : {result.get('grounded_parts_count', '?')}")
    print(f"  │ actuarial      : {result.get('has_actuarial', '?')}")
    print(f"  │ negotiation    : {result.get('has_negotiation', '?')}")
    print(f"  │ elapsed        : {elapsed:.1f}s")

    passed_verdict = _check_pass(video, result)
    print(f"  │ VERDICT        : {'✅ PASS' if passed_verdict else '❌ FAIL'}")
    print(f"  └────────────────────────────────────────────────────────")
    result["verdict"] = "PASS" if passed_verdict else "FAIL"
    return result


def _check_pass(video: dict, result: dict) -> bool:
    """Determine if a test case passed its expected conditions."""
    if video["expect_esc"]:
        # Expect a specific escalation code (e.g. ESC-06 for Camry)
        got_esc = result.get("db_esc") or result.get("esc_code") or ""
        return video["expect_esc"] in str(got_esc)
    else:
        # Expect Stage 2 passed + Stage 3+ reached without false escalation
        stage = str(result.get("db_stage", ""))
        esc = result.get("db_esc") or result.get("esc_code") or ""
        bad_esc = any(e in str(esc) for e in [
            "ESC-07", "ESC-05", "ESC-01", "ESC-02", "ESC-03",
        ])
        stage_ok = any(s in stage.upper() for s in [
            "STAGE_3", "STAGE_4", "STAGE_5", "STAGE_6",
            "VLM", "ACTUARIAL", "NEGOTIAT", "SETTLED", "PRICED",
        ])
        has_actuarial = result.get("has_actuarial", False)
        return (stage_ok or has_actuarial) and not bad_esc


async def main():
    print("\n🚗  SettleAI – Full E2E Video Test Suite")
    print(f"    Backend  : {BASE}")
    print(f"    Videos   : {VIDEO_DIR}")
    print(f"    Running {len(VIDEOS)} test cases\n")

    # Quick health check
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            r = await client.get(f"{BASE}/api/v1/claims?limit=1")
            print(f"✅ Backend health OK (HTTP {r.status_code})")
        except Exception as e:
            print(f"❌ Backend not reachable: {e}")
            sys.exit(1)

    results = []
    for video in VIDEOS:
        result = await upload_and_stream(video, timeout_s=300)
        results.append(result)
        await asyncio.sleep(3)  # brief pause between tests

    # ── Summary ────────────────────────────────────────────────────────────
    print_banner("E2E TEST SUMMARY")
    passes = sum(1 for r in results if r.get("verdict") == "PASS")
    total = len(results)
    for r in results:
        v = r.get("verdict", "?")
        icon = "✅" if v == "PASS" else "❌"
        esc = r.get("db_esc") or r.get("esc_code") or "-"
        stage = r.get("db_stage", r.get("stage_reached", "?"))
        print(f"  {icon}  {r.get('name', '?'):<55} [{v}]  stage={stage}  esc={esc}  {r.get('elapsed_s', '?')}s")
    print(f"\n  Total: {passes}/{total} passed")
    print()
    sys.exit(0 if passes == total else 1)


if __name__ == "__main__":
    asyncio.run(main())

