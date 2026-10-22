#!/usr/bin/env python3
"""
Frontend E2E via Playwright — simulates a judge clicking preset buttons in /new-claim.
Each preset auto-loads the video file + policy + description.
Waits for SSE events to settle, screenshots the final claim page.
"""
import asyncio, time, sys
from pathlib import Path

FRONTEND = "http://localhost:3000"
SUBMIT_TIMEOUT = 180  # seconds to wait for Stage 5 / escalation

PRESETS = [
    {"label_fragment": "car_002",     "expect_esc": None,    "name": "Hyundai Creta"},
    {"label_fragment": "Corolla",     "expect_esc": None,    "name": "Toyota Corolla (side impact)"},
    {"label_fragment": "car_011",     "expect_esc": None,    "name": "Tata Nexon"},
    {"label_fragment": "Camry",       "expect_esc": "ESC-06","name": "Toyota Camry (ESC-06)"},
]

def bar(text):
    print(f"\n{'='*70}\n  {text}\n{'='*70}")

async def run():
    from playwright.async_api import async_playwright

    results = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})

        for preset in PRESETS:
            bar(f"Frontend E2E: {preset['name']}")
            page = await ctx.new_page()
            t0 = time.time()

            # 1. Load /new-claim
            print(f"  → GET {FRONTEND}/new-claim")
            await page.goto(f"{FRONTEND}/new-claim", wait_until="networkidle", timeout=15000)
            await page.screenshot(path=f"/tmp/fe_{preset['name'].replace(' ','_')}_1_loaded.png")

            # 2. Click the matching preset button
            frag = preset["label_fragment"]
            btn_selector = f".preset-btn:has-text('{frag}')"
            try:
                await page.wait_for_selector(btn_selector, timeout=5000)
                await page.click(btn_selector)
                print(f"  → Clicked preset button [{frag}]")
                await asyncio.sleep(2)  # file fetch is async (fetch+blob)
            except Exception as e:
                print(f"  ⚠️  Preset button not found ({frag}): {e}")
                results.append({"name": preset["name"], "verdict": "FAIL", "reason": "preset-btn not found"})
                await page.close()
                continue

            await page.screenshot(path=f"/tmp/fe_{preset['name'].replace(' ','_')}_2_preset.png")

            # 3. Submit the form
            submit_selector = "button[type='submit']"
            try:
                await page.wait_for_selector(submit_selector, timeout=5000)
                await page.click(submit_selector)
                print(f"  → Form submitted")
            except Exception as e:
                print(f"  ⚠️  Submit button not found: {e}")
                results.append({"name": preset["name"], "verdict": "FAIL", "reason": "submit btn not found"})
                await page.close()
                continue

            # 4. Wait for redirect to /claims/[uuid]
            try:
                await page.wait_for_url("**/claims/**", timeout=20000)
                print(f"  → Redirected to {page.url}")
            except Exception:
                print(f"  ⚠️  No redirect to /claims/ within 20s, current URL: {page.url}")

            # 5. Poll for terminal state (Stage 5, ESC-06, ESC-08, or Rejected)
            TERMINAL = [
                "STAGE_5_NEGOTIATION", "PRICED_READY_FOR_NEGOTIATION",
                "Settlement", "Negotiation",
                "ESC-06", "ESC-07", "ESC-08",
                "ESCALATED", "REJECTED",
                "Stage 5", "Stage 4 · Actuarial",
            ]
            print(f"  → Polling for terminal state (up to {SUBMIT_TIMEOUT}s) ...")
            print(f"  {'TIME':>5}  {'URL':<55} STATUS")
            for i in range(SUBMIT_TIMEOUT // 3):
                await asyncio.sleep(3)
                content = await page.content()
                url     = page.url
                hit     = next((s for s in TERMINAL if s in content), None)
                elapsed = round(time.time() - t0, 0)
                print(f"  {elapsed:>5}s  {url[-50:]:<55} {hit or 'processing...'}")
                if hit:
                    break

            elapsed = round(time.time() - t0, 1)
            await page.screenshot(path=f"/tmp/fe_{preset['name'].replace(' ','_')}_3_final.png")

            # 6. Parse page for ESC code and stage
            content = await page.content()
            esc_found = next((c for c in ["ESC-00","ESC-01","ESC-02","ESC-05","ESC-06","ESC-07","ESC-08"] if c in content), None)
            stage_found = next((s for s in [
                "STAGE_5_NEGOTIATION","STAGE_4_ACTUARIAL","STAGE_3_VLM",
                "STAGE_2_SEGMENTATION","STAGE_1_IDENTITY",
                "Stage 5","Stage 4","Negotiation","Settlement","Escalated","Rejected",
            ] if s in content), "UNKNOWN")

            # 7. Verdict
            if preset["expect_esc"] is None:
                # Expect to reach Stage 4/5 with no blocking ESC
                verdict = "PASS" if esc_found not in ["ESC-00","ESC-01","ESC-02","ESC-07"] else "FAIL"
            else:
                verdict = "PASS" if esc_found == preset["expect_esc"] else "FAIL"

            icon = "✅" if verdict == "PASS" else "❌"
            print(f"\n  ┌─ RESULT ──────────────────────────────────────────")
            print(f"  │ url     : {page.url}")
            print(f"  │ stage   : {stage_found}")
            print(f"  │ esc     : {esc_found or '-'}")
            print(f"  │ elapsed : {elapsed}s")
            print(f"  │ VERDICT : {icon} {verdict}")
            print(f"  └────────────────────────────────────────────────────")

            results.append({
                "name": preset["name"], "verdict": verdict,
                "stage": stage_found, "esc": esc_found, "elapsed": elapsed,
            })
            await page.close()

        await browser.close()

    # Summary
    bar("FRONTEND E2E SUMMARY")
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    for r in results:
        icon = "✅" if r["verdict"] == "PASS" else "❌"
        print(f"  {icon}  {r['name']:<45} [{r['verdict']}]  stage={r.get('stage','?')}  esc={r.get('esc') or '-'}  {r.get('elapsed','?')}s")
    print(f"\n  Total: {passed}/{len(results)} passed")
    return passed == len(results)

if __name__ == "__main__":
    ok = asyncio.run(run())
    sys.exit(0 if ok else 1)

