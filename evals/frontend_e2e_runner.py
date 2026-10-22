"""
evals/frontend_e2e_runner.py
Frontend-Matching End-to-End Test Client for Auto-Settle AI.

Simulates the exact HTTP and Server-Sent Events (SSE) protocol used by the
Next.js / React claimant frontend web application:
  1. POST /api/v1/claims/upload (Multi-part video/photo upload + policy + intent)
  2. GET /api/v1/claims/{id}/events (Subscribes to Redis-backed SSE event stream)
  3. GET /api/v1/claims/{id} (State polling & progress monitoring)
  4. POST /api/v1/claims/{id}/negotiate (Claimant conversational turn & counter-offer)
  5. POST /api/v1/claims/{id}/accept (Cryptographic HMAC offer card submission)
  6. GET /api/v1/claims/{id}/voucher/pdf (Official Settlement Voucher PDF download)
     -- OR --
     POST /api/v1/claims/{id}/reject + GET /api/v1/claims/{id}/dossier/pdf (Surveyor escalation)

Can be executed in-process against FastAPI ASGI transport (zero external network setup)
or against a live running server instance (e.g., http://localhost:8000).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import io
import json
from pathlib import Path
import sys
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union
import uuid

import httpx
from httpx import ASGITransport, AsyncClient

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app
from app.infrastructure.db.session import get_db_session
from tests.in_memory_db import (
    FakeAsyncSession,
    in_memory_db,
    patch_in_memory_db,
)

# Patch in-memory repositories for hermetic in-process testing
patch_in_memory_db()


async def _override_db():
    yield FakeAsyncSession()

app.dependency_overrides[get_db_session] = _override_db


class FrontendE2ETestClient:
    """
    High-fidelity E2E simulation client emulating frontend browser interactions.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        artifacts_dir: Union[str, Path] = Path("evals/artifacts/frontend_e2e"),
    ):
        self.base_url = base_url or "http://testserver"
        self.is_in_process = base_url is None
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def _get_client(self) -> AsyncClient:
        if self.is_in_process:
            transport = ASGITransport(app=app)
            return AsyncClient(transport=transport, base_url="http://testserver")
        return AsyncClient(base_url=self.base_url)

    async def execute_full_claim_flow(
        self,
        video_path: Union[str, Path],
        policy_id: str = "POL-HAPPY-001",
        claim_description: str = "Deep scratch on front bumper and front right door",
        counteroffer_inr: Optional[Decimal] = Decimal("9500.00"),
        beneficiary_upi: str = "testclaimant@okhdfcbank",
        should_accept: bool = True,
        rejection_reason: str = "Prefer authorized workshop cashless repair.",
    ) -> Dict[str, Any]:
        """
        Executes complete frontend lifecycle from upload to voucher PDF download.
        """
        v_p = Path(video_path)
        if not v_p.exists():
            raise FileNotFoundError(f"Video not found: {v_p}")

        e2e_log: List[Dict[str, Any]] = []
        t0 = time.perf_counter()

        def _log(step: str, details: Any):
            e2e_log.append({
                "step": step,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": details,
            })

        async with self._get_client() as client:
            # ------------------------------------------------------------------
            # Step 1: Upload Media (Stage 0 Fast-Fail Ingest)
            # ------------------------------------------------------------------
            _log("STEP_1_UPLOAD_REQUEST", {"video": str(v_p), "policy": policy_id})

            with open(v_p, "rb") as vf:
                files = {
                    "video_file": (v_p.name, vf, "video/mp4"),
                }
                data = {
                    "policy_id": policy_id,
                    "claim_description": claim_description,
                    "is_demo_rehearsal": "true",
                }
                upload_resp = await client.post("/api/v1/claims/upload", data=data, files=files)

            if upload_resp.status_code not in (200, 202):
                _log("STEP_1_UPLOAD_FAILED", {"status_code": upload_resp.status_code, "text": upload_resp.text})
                return {
                    "success": False,
                    "terminal_step": "UPLOAD",
                    "error": f"Upload failed ({upload_resp.status_code}): {upload_resp.text}",
                    "log": e2e_log,
                }

            upload_data = upload_resp.json()
            claim_id_str = upload_data.get("claim_id")
            if not claim_id_str:
                return {
                    "success": False,
                    "terminal_step": "UPLOAD",
                    "error": "No claim_id returned in upload response",
                    "response": upload_data,
                    "log": e2e_log,
                }

            claim_id = uuid.UUID(claim_id_str)
            _log("STEP_1_UPLOAD_SUCCESS", {"claim_id": str(claim_id), "response": upload_data})

            # Check if Stage 0 passed or rejected
            if not upload_data.get("passed", False):
                _log("STEP_1_FAST_FAIL_REJECTION", upload_data)
                return {
                    "success": True,
                    "terminal_step": "FAST_FAIL_REJECTED",
                    "claim_id": str(claim_id),
                    "verdict": "REJECTED_STAGE0",
                    "remediation": upload_data.get("remediation"),
                    "log": e2e_log,
                }

            # ------------------------------------------------------------------
            # Step 2: Poll Claim State Until Negotiation Session is Initialized
            # ------------------------------------------------------------------
            _log("STEP_2_WAIT_FOR_PROCESSING", {"claim_id": str(claim_id)})
            session_data = None
            max_retries = 30
            poll_interval = 0.5

            for attempt in range(max_retries):
                # Poll negotiation endpoint
                neg_resp = await client.get(f"/api/v1/claims/{claim_id}/negotiation")
                if neg_resp.status_code == 200:
                    session_data = neg_resp.json()
                    _log("STEP_2_NEGOTIATION_READY", session_data)
                    break

                # Also poll claim status to check for early escalation
                claim_resp = await client.get(f"/api/v1/claims/{claim_id}")
                if claim_resp.status_code == 200:
                    c_data = claim_resp.json()
                    c_status = c_data.get("claim_status", "")
                    if "REJECTED" in c_status or "ESCALATED" in c_status:
                        _log("STEP_2_EARLY_ESCALATION", c_data)
                        return {
                            "success": True,
                            "terminal_step": "PIPELINE_ESCALATED",
                            "claim_id": str(claim_id),
                            "claim_status": c_status,
                            "escalation_code": c_data.get("escalation_code"),
                            "log": e2e_log,
                        }

                await asyncio.sleep(poll_interval)

            if not session_data:
                # If background task didn't finish or hit escalation
                claim_resp = await client.get(f"/api/v1/claims/{claim_id}")
                return {
                    "success": False,
                    "terminal_step": "TIMEOUT_WAITING_NEGOTIATION",
                    "claim_id": str(claim_id),
                    "claim_details": claim_resp.json() if claim_resp.status_code == 200 else None,
                    "log": e2e_log,
                }

            # ------------------------------------------------------------------
            # Step 3: Interactive Negotiation Turn (Frontend Chatbot Interface)
            # ------------------------------------------------------------------
            active_offer = session_data.get("active_offer_card", {})
            initial_amount = active_offer.get("amount_inr")
            _log("STEP_3_INITIAL_OFFER_PRESENTED", active_offer)

            current_offer_card = active_offer

            if counteroffer_inr is not None and counteroffer_inr > Decimal("0.00"):
                _log("STEP_3_SEND_COUNTEROFFER", {"counteroffer_inr": str(counteroffer_inr)})
                neg_payload = {
                    "message": f"I obtained an estimate from an authorized bodyshop for ₹{counteroffer_inr:,.2f}. Can you please improve your offer?",
                    "counteroffer_inr": str(counteroffer_inr),
                }
                turn_resp = await client.post(f"/api/v1/claims/{claim_id}/negotiate", json=neg_payload)
                if turn_resp.status_code == 200:
                    turn_data = turn_resp.json()
                    current_offer_card = turn_data.get("offer_card", active_offer)
                    _log("STEP_3_COUNTEROFFER_ACCEPTED_BY_BOT", turn_data)
                else:
                    _log("STEP_3_COUNTEROFFER_ERROR", {"status": turn_resp.status_code, "text": turn_resp.text})

            # ------------------------------------------------------------------
            # Step 4: Accept Offer OR Reject and Escalate
            # ------------------------------------------------------------------
            if should_accept:
                _log("STEP_4_ACCEPT_OFFER", {"offer_card": current_offer_card, "upi": beneficiary_upi})
                accept_payload = {
                    "offer_card": current_offer_card,
                    "beneficiary_upi_id": beneficiary_upi,
                }
                accept_resp = await client.post(f"/api/v1/claims/{claim_id}/accept", json=accept_payload)
                if accept_resp.status_code != 200:
                    _log("STEP_4_ACCEPT_FAILED", {"status": accept_resp.status_code, "text": accept_resp.text})
                    return {
                        "success": False,
                        "terminal_step": "ACCEPT_OFFER",
                        "error": f"Offer acceptance rejected: {accept_resp.text}",
                        "log": e2e_log,
                    }

                voucher_data = accept_resp.json()
                _log("STEP_4_SETTLEMENT_VOUCHER_ISSUED", voucher_data)

                # Step 5: Download Official PDF Voucher
                pdf_resp = await client.get(f"/api/v1/claims/{claim_id}/voucher/pdf")
                assert pdf_resp.status_code == 200
                assert pdf_resp.content.startswith(b"%PDF")
                pdf_path = self.artifacts_dir / f"voucher_{claim_id}.pdf"
                pdf_path.write_bytes(pdf_resp.content)
                _log("STEP_5_PDF_VOUCHER_DOWNLOADED", {"path": str(pdf_path), "bytes": len(pdf_resp.content)})

                total_time = round((time.perf_counter() - t0) * 1000.0, 2)
                return {
                    "success": True,
                    "terminal_step": "SETTLED_CASH",
                    "claim_id": str(claim_id),
                    "voucher_id": voucher_data.get("voucher_id"),
                    "settled_amount_inr": voucher_data.get("settled_amount_inr"),
                    "beneficiary_upi_id": voucher_data.get("beneficiary_upi_id"),
                    "pdf_voucher_path": str(pdf_path),
                    "total_latency_ms": total_time,
                    "log": e2e_log,
                }

            else:
                # Reject offer -> route to surveyor dossier
                _log("STEP_4_REJECT_OFFER", {"reason": rejection_reason})
                reject_payload = {"reason": rejection_reason}
                reject_resp = await client.post(f"/api/v1/claims/{claim_id}/reject", json=reject_payload)
                if reject_resp.status_code != 200:
                    _log("STEP_4_REJECT_FAILED", {"status": reject_resp.status_code, "text": reject_resp.text})
                    return {
                        "success": False,
                        "terminal_step": "REJECT_OFFER",
                        "error": f"Rejection failed: {reject_resp.text}",
                        "log": e2e_log,
                    }

                dossier_data = reject_resp.json()
                _log("STEP_4_SURVEYOR_DOSSIER_COMPILED", dossier_data)

                # Download Surveyor PDF Dossier
                pdf_resp = await client.get(f"/api/v1/claims/{claim_id}/dossier/pdf")
                assert pdf_resp.status_code == 200
                assert pdf_resp.content.startswith(b"%PDF")
                pdf_path = self.artifacts_dir / f"dossier_{claim_id}.pdf"
                pdf_path.write_bytes(pdf_resp.content)
                _log("STEP_5_PDF_DOSSIER_DOWNLOADED", {"path": str(pdf_path), "bytes": len(pdf_resp.content)})

                total_time = round((time.perf_counter() - t0) * 1000.0, 2)
                return {
                    "success": True,
                    "terminal_step": "ESCALATED_HUMAN",
                    "claim_id": str(claim_id),
                    "dossier_id": dossier_data.get("dossier_id"),
                    "pdf_dossier_path": str(pdf_path),
                    "total_latency_ms": total_time,
                    "log": e2e_log,
                }
