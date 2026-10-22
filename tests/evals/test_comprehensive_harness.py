"""
tests/evals/test_comprehensive_harness.py
Comprehensive test suite validating the Master Evaluation Harness, Stage Bypassing,
Audit Trails, and Frontend-like E2E flows.
"""
from decimal import Decimal
import json
from pathlib import Path
import pytest
import uuid

from evals.comprehensive_harness import (
    AuditTrail,
    ComprehensiveEvaluationHarness,
    extract_uniform_keyframes_from_video,
)
from evals.frontend_e2e_runner import FrontendE2ETestClient
from evals.web_testbench import testbench_app as tb_app
from httpx import ASGITransport, AsyncClient
from tests.in_memory_db import in_memory_db

TEST_VIDEOS_DIR = Path("test_assets/videos")
REAL_HILUX = TEST_VIDEOS_DIR / "difficult/toyota_hilux_white_ute.mp4"
CAR_001 = TEST_VIDEOS_DIR / "simple/car_001.mp4"


@pytest.fixture(autouse=True)
def clean_db():
    """Resets in-memory DB and unrepaired claims before every test for clean isolation."""
    in_memory_db.reset()
    yield
    in_memory_db.reset()


@pytest.fixture
def eval_harness(tmp_path):
    return ComprehensiveEvaluationHarness(
        output_artifacts_dir=tmp_path / "artifacts",
        vlm_provider="mock",
    )


class TestKeyframeExtraction:
    """Verifies OpenCV keyframe sampler when Stage 1 is bypassed or video has cuts."""

    def test_extract_uniform_keyframes_from_video(self, tmp_path):
        assert CAR_001.exists(), f"Missing test video {CAR_001}"
        out_dir = tmp_path / "kfs"
        kfs = extract_uniform_keyframes_from_video(CAR_001, out_dir, target_count=6)

        assert len(kfs) == 6
        for name, p_str in kfs.items():
            p = Path(p_str)
            assert p.exists()
            assert p.stat().st_size > 1000
            assert name.startswith("keyframe_")


class TestStageBypassingAndEvaluation:
    """Tests selective stage bypassing and full end-to-end execution."""

    @pytest.mark.asyncio
    async def test_harness_bypass_stage0_and_stage1_cuts(self, eval_harness):
        """
        User requirement: Test video with cuts or non-standard container by bypassing
        Stage 0 and Stage 1 to test Stage 2 and 3 downstream.
        """
        audit: AuditTrail = await eval_harness.evaluate(
            media_path=CAR_001,
            claim_description="Scratched front bumper",
            policy_id="POL-HAPPY-001",
            bypass_stages=["stage_0", "stage_1"],
            overrides={"force_continue": True},
        )

        assert audit.stage_audits["stage_0"].status == "BYPASSED"
        assert audit.stage_audits["stage_1"].status == "BYPASSED"
        assert audit.stage_audits["stage_1"].outputs_summary["keyframes_extracted"] >= 6
        assert "stage_2" in audit.stage_audits
        assert "stage_3" in audit.stage_audits
        assert audit.stage_audits["stage_2"].latency_ms > 0

    @pytest.mark.asyncio
    async def test_harness_simulated_damage_full_financial_and_settlement(self, eval_harness):
        """
        Tests entire pipeline down to cash voucher generation with itemized IRDAI math.
        """
        audit: AuditTrail = await eval_harness.evaluate(
            media_path=REAL_HILUX,
            claim_description="Scratched front bumper",
            policy_id="POL-HILUX-010",
            bypass_stages=["stage_0", "stage_1", "stage_2"],
            negotiation_strategy="counter_then_accept",
        )

        assert audit.final_verdict == "SETTLED_CASH"
        assert audit.stage_audits["stage_3"].status == "PASSED"
        assert audit.stage_audits["stage_4"].status == "PASSED"
        assert audit.stage_audits["stage_5"].status == "PASSED"
        assert audit.stage_audits["stage_6"].status == "SETTLED_CASH"

        # Check financial integrity
        fin = audit.financial_summary
        assert Decimal(fin["gross_repair_inr"]) > Decimal("0.00")
        assert Decimal(fin["net_liability_inr"]) > Decimal("0.00")
        assert Decimal(fin["initial_offer_inr"]) > Decimal("0.00")

        # Check negotiation concession
        neg = audit.negotiation_summary
        assert len(neg["turns"]) >= 1
        assert len(neg["hmac_signature"]) == 64  # SHA-256 HMAC

        # Check voucher PDF
        pdf_path = Path(audit.generated_artifacts["voucher_pdf"])
        assert pdf_path.exists()
        assert pdf_path.read_bytes().startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_harness_rejection_and_surveyor_dossier_pdf(self, eval_harness):
        """
        Tests escalation path where claimant rejects cash offer and system compiles
        the Surveyor Claims Review Dossier and printable PDF.
        """
        audit: AuditTrail = await eval_harness.evaluate(
            media_path=REAL_HILUX,
            claim_description="Scratched front bumper",
            policy_id="POL-HILUX-010",
            bypass_stages=["stage_0", "stage_1", "stage_2"],
            negotiation_strategy="reject_to_surveyor",
        )

        assert audit.final_verdict == "ESCALATED_HUMAN"
        assert audit.stage_audits["stage_6"].status == "ESCALATED_HUMAN"
        assert "dossier_pdf" in audit.generated_artifacts

        dossier_pdf = Path(audit.generated_artifacts["dossier_pdf"])
        assert dossier_pdf.exists()
        assert dossier_pdf.read_bytes().startswith(b"%PDF")

    @pytest.mark.asyncio
    async def test_audit_trail_serialization(self, eval_harness):
        """Validates that AuditTrail serializes cleanly to JSON and writes audit_trail.json."""
        audit: AuditTrail = await eval_harness.evaluate(
            media_path=CAR_001,
            claim_description="Scratched front bumper",
            policy_id="POL-HAPPY-001",
            bypass_stages=["stage_0", "stage_1", "stage_2"],
        )

        audit_json = audit.to_json(indent=2)
        parsed = json.loads(audit_json)
        assert parsed["claim_id"] == audit.claim_id
        assert len(parsed["stage_audits"]) in (8, 9)
        assert "audit_trail_json" in audit.generated_artifacts
        assert Path(audit.generated_artifacts["audit_trail_json"]).exists()


class TestWebTestbenchEndpoints:
    """Tests the interactive Web Testbench FastAPI routes."""

    @pytest.mark.asyncio
    async def test_testbench_dashboard_html(self):
        transport = ASGITransport(app=tb_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            assert resp.status_code == 200
            assert "Auto-Settle AI" in resp.text
            assert "Evaluation Parameters" in resp.text

    @pytest.mark.asyncio
    async def test_testbench_run_api(self):
        transport = ASGITransport(app=tb_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "media_path": str(CAR_001),
                "claim_description": "Scratched front bumper",
                "policy_id": "POL-HAPPY-001",
                "bypass_stages": ["stage_0", "stage_1", "stage_2"],
                "negotiation_strategy": "counter_then_accept",
            }
            resp = await client.post("/api/testbench/run", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["final_verdict"] == "SETTLED_CASH"
            assert "stage_audits" in data
            claim_id = data["claim_id"]

            # Test PDF download endpoint
            pdf_resp = await client.get(f"/api/testbench/{claim_id}/pdf")
            assert pdf_resp.status_code == 200
            assert pdf_resp.headers["content-type"] == "application/pdf"
            assert pdf_resp.content.startswith(b"%PDF")
