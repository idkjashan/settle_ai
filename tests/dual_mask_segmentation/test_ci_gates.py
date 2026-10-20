"""
tests/dual_mask_segmentation/test_ci_gates.py
Pytest integration wrapper for Stage 2 CI Gate Invariants.
"""
import pytest
from evals.dual_mask_segmentation.ci_gate_assertions import Stage2CIGateSuite


class TestStage2CIGates:
    @pytest.fixture
    def suite(self) -> Stage2CIGateSuite:
        return Stage2CIGateSuite()

    def test_gate_1_iop_error_ceiling(self, suite: Stage2CIGateSuite):
        max_err = suite.evaluate_invariant_1_iop_error()
        assert max_err <= 0.015

    def test_gate_2_zoom_anti_inflation(self, suite: Stage2CIGateSuite):
        false_rep_rate = suite.evaluate_invariant_2_zoom_anti_inflation()
        assert false_rep_rate == 0.0

    @pytest.mark.asyncio
    async def test_gate_3_sql_catalogue_hit_rate(self, suite: Stage2CIGateSuite):
        hit_rate = await suite.evaluate_invariant_3_sql_catalogue_hit_rate()
        assert hit_rate == 1.0

    def test_gate_4_som_interior_occlusion_rate(self, suite: Stage2CIGateSuite):
        occlusion_rate = suite.evaluate_invariant_4_som_interior_occlusion()
        assert occlusion_rate == 0.0

    @pytest.mark.asyncio
    async def test_gate_5_latency_sla_guardrails(self, suite: Stage2CIGateSuite):
        p50, p95 = await suite.evaluate_invariant_5_latency_guardrails()
        assert p50 <= 240.0
        assert p95 <= 420.0
