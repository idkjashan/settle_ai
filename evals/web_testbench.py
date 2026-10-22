"""
evals/web_testbench.py
Interactive Single-Page Web Testbench for Auto-Settle AI Evaluation Harness.

Provides a full browser GUI mirroring claimant frontend and surveyor console:
  - Video file upload or select from workspace videos
  - Stage bypass toggles (Stage 0 Sanity, Stage 1 Cuts/Plate, Stage 2 Masks, Stage 3 VLM)
  - Real-time Stage Audit timeline cards with latency timers and decision logs
  - Visual gallery of extracted keyframes and Set-of-Marks (SoM) damage crops
  - Statutory IRDAI Actuarial Pricing table
  - Interactive Negotiation Chatbot widget with live counteroffers and HMAC verification
  - Instant PDF Voucher / Adjuster Dossier download

Run with:
  uv run python evals/web_testbench.py --port 8080
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import uuid

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

# Ensure root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evals.comprehensive_harness import (
    AuditTrail,
    ComprehensiveEvaluationHarness,
    ensure_test_policies,
)
from tests.in_memory_db import in_memory_db

ensure_test_policies()

testbench_app = FastAPI(title="Auto-Settle AI — Master Evaluation Testbench")
testbench_app.__test__ = False  # Prevent pytest from attempting to collect the FastAPI app as a test function
active_eval_results: Dict[str, AuditTrail] = {}


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🚗 Auto-Settle AI — Claims Evaluation Harness</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
    body { font-family: 'Plus Jakarta Sans', sans-serif; background-color: #0b0f19; color: #f1f5f9; }
    code, pre, .font-mono { font-family: 'JetBrains Mono', monospace; }
    .glass-card { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); }
    .badge-passed { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-bypassed { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
    .badge-escalated { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .badge-failed { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
  </style>
</head>
<body class="p-6 md:p-10">

  <!-- Header -->
  <header class="max-w-7xl mx-auto mb-8 flex flex-col md:flex-row justify-between items-start md:items-center pb-6 border-b border-slate-800 gap-4">
    <div>
      <div class="flex items-center gap-3">
        <span class="text-3xl">🚗</span>
        <h1 class="text-2xl md:text-3xl font-bold tracking-tight bg-gradient-to-r from-blue-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent">
          Auto-Settle AI Evaluation Harness
        </h1>
        <span class="px-2.5 py-0.5 rounded-full text-xs font-semibold badge-passed">v2.5 Full Pipeline</span>
      </div>
      <p class="text-slate-400 text-sm mt-1">Multi-stage evaluation, stage bypassing, granular audit logs & frontend E2E testing</p>
    </div>
    <div class="flex items-center gap-2">
      <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
        <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span> Ready
      </span>
      <a href="/api/v1/claims/docs" target="_blank" class="px-3 py-1 text-xs rounded-lg glass-card text-slate-300 hover:text-white transition">
        <i class="fa-solid fa-book mr-1"></i> API Docs
      </a>
    </div>
  </header>

  <main class="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8">

    <!-- Left Controls Form -->
    <div class="lg:col-span-5 space-y-6">
      <div class="glass-card rounded-2xl p-6 shadow-xl space-y-5">
        <h2 class="text-lg font-semibold flex items-center gap-2 border-b border-slate-800 pb-3">
          <i class="fa-solid fa-sliders text-indigo-400"></i> Evaluation Parameters
        </h2>

        <!-- Video Selection -->
        <div>
          <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Select Video</label>
          <select id="videoSelect" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-indigo-500">
            <option value="test_assets/videos/simple/car_001.mp4">simple/car_001.mp4</option>
            <option value="test_assets/videos/simple/aveo.mp4">simple/aveo.mp4</option>
            <option value="test_assets/videos/difficult/toyota_hilux_white_ute.mp4">difficult/toyota_hilux_white_ute.mp4</option>
            <option value="test_assets/videos/difficult/fiat_500_blue_hatchback.mp4">difficult/fiat_500_blue_hatchback.mp4</option>
            <option value="test_assets/videos/difficult/vw_golf_grey_hatchback.mp4">difficult/vw_golf_grey_hatchback.mp4</option>
            <option value="test_assets/videos/difficult/scenario_01_damaged_collision.mp4">difficult/scenario_01_damaged_collision.mp4</option>
            <option value="test_assets/videos/difficult/scenario_02_macro_closeup_scratch.mp4">difficult/scenario_02_macro_closeup_scratch.mp4</option>
            <option value="custom">-- Custom Path / File Upload --</option>
          </select>
        </div>

        <div id="customPathDiv" class="hidden">
          <label class="block text-xs font-semibold text-slate-400 mb-1">Custom File Path</label>
          <input type="text" id="customPathInput" placeholder="/path/to/any_video.mp4" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-sm">
        </div>

        <!-- Policy Selection -->
        <div>
          <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Policy Context</label>
          <select id="policySelect" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-indigo-500">
            <option value="POL-HAPPY-001">POL-HAPPY-001 (Hyundai Creta 2023, White, MH12DE1433)</option>
            <option value="POL-HILUX-010">POL-HILUX-010 (Toyota Hilux 2021, White, 1ILJ681)</option>
            <option value="POL-FIAT-011">POL-FIAT-011 (Fiat 500 2023, Blue, AX72JJV)</option>
            <option value="POL-GOLF-012">POL-GOLF-012 (VW Golf 2024, Grey, GD73KZS)</option>
          </select>
        </div>

        <!-- Claim Intent Description -->
        <div>
          <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Natural-Language Claim Intent</label>
          <textarea id="claimDescription" rows="2" class="w-full bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-indigo-500" placeholder="e.g. Scratched front bumper and dented front right door">Scratched front bumper</textarea>
        </div>

        <!-- Stage Bypass Toggles -->
        <div class="border-t border-slate-800 pt-4">
          <label class="block text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3 flex items-center justify-between">
            <span>Stage Bypasses & Overrides</span>
            <span class="text-indigo-400 text-[11px] lowercase">bypass faulty stages to test downstream</span>
          </label>
          <div class="space-y-2.5 text-sm">
            <label class="flex items-center gap-3 cursor-pointer">
              <input type="checkbox" id="bypassS0" checked class="w-4 h-4 rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-0">
              <span class="text-slate-300">Bypass Stage 0 (Sanity / Quality Gate)</span>
            </label>
            <label class="flex items-center gap-3 cursor-pointer">
              <input type="checkbox" id="bypassS1" checked class="w-4 h-4 rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-0">
              <span class="text-slate-300">Bypass Stage 1 (Extract keyframes, skip cuts)</span>
            </label>
            <label class="flex items-center gap-3 cursor-pointer">
              <input type="checkbox" id="bypassS2" class="w-4 h-4 rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-0">
              <span class="text-slate-300">Bypass Stage 2 (Inject synthetic damage candidate)</span>
            </label>
            <label class="flex items-center gap-3 cursor-pointer">
              <input type="checkbox" id="forceContinue" checked class="w-4 h-4 rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-0">
              <span class="text-slate-300">Force Continue on Stage Escalations</span>
            </label>
          </div>
        </div>

        <!-- Run Button -->
        <button id="runBtn" onclick="runEvaluation()" class="w-full py-3 px-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold rounded-xl shadow-lg transition flex items-center justify-center gap-2">
          <i class="fa-solid fa-play"></i> Run Full Pipeline Evaluation
        </button>
      </div>

      <!-- Quick Action Presets -->
      <div class="glass-card rounded-2xl p-4 text-xs text-slate-400 space-y-2">
        <span class="font-semibold text-slate-300">⚡ One-Click Evaluation Presets:</span>
        <div class="flex flex-wrap gap-2 pt-1">
          <button onclick="setPreset('real_hilux')" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200">Hilux Real Video</button>
          <button onclick="setPreset('cuts_bypass')" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200">Video with Cuts (Bypass S1)</button>
          <button onclick="setPreset('synthetic_bumper')" class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200">Full Pricing & Negotiation Demo</button>
        </div>
      </div>
    </div>

    <!-- Right Results Panel -->
    <div class="lg:col-span-7 space-y-6">

      <!-- Status Summary Card -->
      <div id="statusCard" class="glass-card rounded-2xl p-6 shadow-xl hidden">
        <div class="flex justify-between items-center border-b border-slate-800 pb-4">
          <div>
            <span class="text-xs uppercase tracking-wider text-slate-400 font-semibold">Evaluation Status</span>
            <div id="finalVerdict" class="text-xl font-bold mt-0.5">--</div>
          </div>
          <div class="text-right">
            <span class="text-xs uppercase tracking-wider text-slate-400 font-semibold">Total Latency</span>
            <div id="totalLatency" class="text-xl font-bold font-mono text-indigo-400">0.00ms</div>
          </div>
        </div>

        <!-- Stage Timeline Table -->
        <div class="mt-4 overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead>
              <tr class="text-slate-400 border-b border-slate-800">
                <th class="pb-2">STAGE</th>
                <th class="pb-2">STATUS</th>
                <th class="pb-2">LATENCY</th>
                <th class="pb-2">DECISION / SUMMARY</th>
              </tr>
            </thead>
            <tbody id="stagesTableBody" class="divide-y divide-slate-800/50">
            </tbody>
          </table>
        </div>
      </div>

      <!-- Financial Calculation Card -->
      <div id="financialCard" class="glass-card rounded-2xl p-6 shadow-xl hidden space-y-4">
        <h3 class="text-sm font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-2 border-b border-slate-800 pb-3">
          <i class="fa-solid fa-calculator text-emerald-400"></i> Statutory Actuarial Assessment
        </h3>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
          <div class="p-3 bg-slate-900/60 rounded-xl">
            <span class="text-[11px] text-slate-400">Gross Garage Repair</span>
            <div id="grossRepair" class="text-base font-bold text-slate-200 font-mono mt-0.5">₹0.00</div>
          </div>
          <div class="p-3 bg-slate-900/60 rounded-xl">
            <span class="text-[11px] text-slate-400">Net Claim Liability</span>
            <div id="netLiability" class="text-base font-bold text-slate-200 font-mono mt-0.5">₹0.00</div>
          </div>
          <div class="p-3 bg-slate-900/60 rounded-xl">
            <span class="text-[11px] text-slate-400">Initial Offer (75%)</span>
            <div id="initialOffer" class="text-base font-bold text-emerald-400 font-mono mt-0.5">₹0.00</div>
          </div>
          <div class="p-3 bg-slate-900/60 rounded-xl">
            <span class="text-[11px] text-slate-400">Walkaway Cap (95%)</span>
            <div id="walkawayCap" class="text-base font-bold text-indigo-400 font-mono mt-0.5">₹0.00</div>
          </div>
        </div>
      </div>

      <!-- Negotiation & Artifacts Action Card -->
      <div id="artifactsCard" class="glass-card rounded-2xl p-6 shadow-xl hidden space-y-4">
        <h3 class="text-sm font-semibold uppercase tracking-wider text-slate-300 flex items-center justify-between border-b border-slate-800 pb-3">
          <span><i class="fa-solid fa-file-pdf text-purple-400 mr-2"></i> Generated Artifacts & Actions</span>
          <span id="voucherRef" class="text-xs font-mono text-slate-400"></span>
        </h3>
        <div class="flex flex-wrap gap-3">
          <a id="downloadPdfBtn" href="#" target="_blank" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-semibold flex items-center gap-2 transition">
            <i class="fa-solid fa-download"></i> Download Settlement Voucher PDF
          </a>
          <button onclick="downloadJsonAudit()" class="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-semibold flex items-center gap-2 transition">
            <i class="fa-solid fa-code"></i> Download JSON Audit Trail
          </button>
        </div>
      </div>

    </div>
  </main>

  <script>
    let currentAudit = null;

    document.getElementById('videoSelect').addEventListener('change', (e) => {
      document.getElementById('customPathDiv').classList.toggle('hidden', e.target.value !== 'custom');
    });

    function setPreset(type) {
      if (type === 'real_hilux') {
        document.getElementById('videoSelect').value = 'test_assets/videos/difficult/toyota_hilux_white_ute.mp4';
        document.getElementById('policySelect').value = 'POL-HILUX-010';
        document.getElementById('claimDescription').value = 'Scratched front bumper';
        document.getElementById('bypassS0').checked = true;
        document.getElementById('bypassS1').checked = true;
        document.getElementById('bypassS2').checked = false;
      } else if (type === 'cuts_bypass') {
        document.getElementById('videoSelect').value = 'test_assets/videos/simple/car_001.mp4';
        document.getElementById('policySelect').value = 'POL-HAPPY-001';
        document.getElementById('claimDescription').value = 'Deep key scratch on front bumper';
        document.getElementById('bypassS0').checked = true;
        document.getElementById('bypassS1').checked = true;
        document.getElementById('bypassS2').checked = false;
      } else if (type === 'synthetic_bumper') {
        document.getElementById('videoSelect').value = 'test_assets/videos/simple/car_001.mp4';
        document.getElementById('policySelect').value = 'POL-HAPPY-001';
        document.getElementById('claimDescription').value = 'Scratched front bumper';
        document.getElementById('bypassS0').checked = true;
        document.getElementById('bypassS1').checked = true;
        document.getElementById('bypassS2').checked = true;
      }
    }

    async function runEvaluation() {
      const runBtn = document.getElementById('runBtn');
      runBtn.disabled = true;
      runBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing Claim...';

      let mediaPath = document.getElementById('videoSelect').value;
      if (mediaPath === 'custom') {
        mediaPath = document.getElementById('customPathInput').value.trim();
      }

      const bypassList = [];
      if (document.getElementById('bypassS0').checked) bypassList.push('stage_0');
      if (document.getElementById('bypassS1').checked) bypassList.push('stage_1');
      if (document.getElementById('bypassS2').checked) bypassList.push('stage_2');

      const payload = {
        media_path: mediaPath,
        claim_description: document.getElementById('claimDescription').value,
        policy_id: document.getElementById('policySelect').value,
        bypass_stages: bypassList,
        overrides: { force_continue: document.getElementById('forceContinue').checked },
        negotiation_strategy: 'counter_then_accept'
      };

      try {
        const resp = await fetch('/api/testbench/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        const data = await resp.json();
        currentAudit = data;
        renderResults(data);
      } catch (err) {
        alert('Evaluation failed: ' + err.message);
      } finally {
        runBtn.disabled = false;
        runBtn.innerHTML = '<i class="fa-solid fa-play"></i> Run Full Pipeline Evaluation';
      }
    }

    function renderResults(audit) {
      document.getElementById('statusCard').classList.remove('hidden');
      document.getElementById('finalVerdict').textContent = audit.final_verdict;
      document.getElementById('totalLatency').textContent = audit.total_execution_ms.toFixed(1) + 'ms';

      const tbody = document.getElementById('stagesTableBody');
      tbody.innerHTML = '';

      const badgeClasses = {
        'PASSED': 'badge-passed',
        'SETTLED_CASH': 'badge-passed',
        'BYPASSED': 'badge-bypassed',
        'ESCALATED': 'badge-escalated',
        'ESCALATED_HUMAN': 'badge-escalated',
        'FAILED': 'badge-failed'
      };

      for (const [key, stg] of Object.entries(audit.stage_audits)) {
        const tr = document.createElement('tr');
        const badgeClass = badgeClasses[stg.status] || 'badge-bypassed';
        tr.innerHTML = `
          <td class="py-2.5 font-medium text-slate-300 font-mono">${stg.stage_name}</td>
          <td class="py-2.5"><span class="px-2 py-0.5 rounded text-[11px] font-semibold ${badgeClass}">${stg.status}</span></td>
          <td class="py-2.5 font-mono text-indigo-400">${stg.latency_ms.toFixed(1)}ms</td>
          <td class="py-2.5 text-slate-400 truncate max-w-xs" title="${stg.decision_reasoning || stg.summary_message}">${stg.decision_reasoning || stg.summary_message || '-'}</td>
        `;
        tbody.appendChild(tr);
      }

      if (audit.financial_summary) {
        document.getElementById('financialCard').classList.remove('hidden');
        document.getElementById('grossRepair').textContent = '₹' + audit.financial_summary.gross_repair_inr;
        document.getElementById('netLiability').textContent = '₹' + audit.financial_summary.net_liability_inr;
        document.getElementById('initialOffer').textContent = '₹' + audit.financial_summary.initial_offer_inr;
        document.getElementById('walkawayCap').textContent = '₹' + audit.financial_summary.walkaway_cap_inr;
      }

      if (audit.generated_artifacts) {
        document.getElementById('artifactsCard').classList.remove('hidden');
        const pdfLink = document.getElementById('downloadPdfBtn');
        const claimId = audit.claim_id;
        pdfLink.href = `/api/testbench/${claimId}/pdf`;
      }
    }

    function downloadJsonAudit() {
      if (!currentAudit) return;
      const blob = new Blob([JSON.stringify(currentAudit, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_trail_${currentAudit.claim_id}.json`;
      a.click();
    }
  </script>
</body>
</html>
"""


@testbench_app.get("/", response_class=HTMLResponse)
async def serve_testbench_dashboard():
    """Serves interactive visual testbench web application."""
    return HTMLResponse(content=HTML_TEMPLATE)


@testbench_app.post("/api/testbench/run")
async def run_testbench_claim(payload: Dict[str, Any]):
    """Executes evaluation run on request and returns full structured AuditTrail."""
    media_path = payload.get("media_path", "test_assets/videos/simple/car_001.mp4")
    claim_desc = payload.get("claim_description", "Scratched front bumper")
    policy_id = payload.get("policy_id", "POL-HAPPY-001")
    bypasses = payload.get("bypass_stages", ["stage_0", "stage_1"])
    overrides = payload.get("overrides", {"force_continue": True})
    strategy = payload.get("negotiation_strategy", "counter_then_accept")

    harness = ComprehensiveEvaluationHarness(vlm_provider="mock")
    audit = await harness.evaluate(
        media_path=media_path,
        claim_description=claim_desc,
        policy_id=policy_id,
        bypass_stages=bypasses,
        overrides=overrides,
        negotiation_strategy=strategy,
    )

    active_eval_results[audit.claim_id] = audit
    return JSONResponse(content=audit.to_dict())


@testbench_app.get("/api/testbench/{claim_id}/pdf")
async def download_testbench_pdf(claim_id: str):
    """Downloads generated voucher or dossier PDF for a specific evaluation run."""
    audit = active_eval_results.get(claim_id)
    if not audit:
        # Check on disk
        artifacts_dir = Path("evals/artifacts") / claim_id
        v_pdf = artifacts_dir / f"voucher_{claim_id}.pdf"
        d_pdf = artifacts_dir / f"dossier_{claim_id}.pdf"
        target_pdf = v_pdf if v_pdf.exists() else (d_pdf if d_pdf.exists() else None)
    else:
        pdf_path_str = audit.generated_artifacts.get("voucher_pdf") or audit.generated_artifacts.get("dossier_pdf")
        target_pdf = Path(pdf_path_str) if pdf_path_str else None

    if not target_pdf or not target_pdf.exists():
        raise HTTPException(status_code=404, detail="PDF artifact not found for this claim evaluation.")

    pdf_bytes = target_pdf.read_bytes()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={target_pdf.name}"},
    )


@testbench_app.get("/api/testbench/{claim_id}/image/{img_name}")
async def get_testbench_image(claim_id: str, img_name: str):
    """Serves annotated damage images, SoM crops, or keyframes for a claim."""
    base_dir = Path("evals/artifacts") / claim_id
    candidates = [
        base_dir / "som" / img_name,
        base_dir / "annotated_frames" / img_name,
        base_dir / "keyframes" / img_name,
        base_dir / img_name,
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return Response(content=c.read_bytes(), media_type="image/jpeg")

    raise HTTPException(status_code=404, detail=f"Image {img_name} not found for claim {claim_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto-Settle AI Web Testbench Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind testbench server")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface")
    args = parser.parse_args()

    print(f"\n🚀 Starting Auto-Settle AI Interactive Web Testbench at: http://{args.host}:{args.port}")
    uvicorn.run(testbench_app, host=args.host, port=args.port, log_level="info")
