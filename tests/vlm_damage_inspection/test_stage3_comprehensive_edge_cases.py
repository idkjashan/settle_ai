"""Comprehensive edge-case, security gate, and resilience tests for Stage 3 VLM Damage Inspection."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.domain.dual_mask_segmentation.schemas import (
    GroundedDamagedPart,
    OEMPartCatalogueRecord,
    Stage3HandoffPayload,
    SVGOverlayPayload,
)
from app.domain.vlm_damage_inspection import (
    CircuitBreaker,
    DepthGrade,
    DeterministicMockVLMAdapter,
    FalsePositiveReason,
    ForensicDecisionEngine,
    InspectionContext,
    QuarantinedPartRecord,
    ResilientJSONParser,
    Stage3CircuitBreakerOpenError,
    Stage3FailureCode,
    Stage3InspectionError,
    Stage3MalformedOutputError,
    Stage3NoRealDamageDetectedError,
    Stage3ProviderUnreachableError,
    Stage3RustOrOxidationError,
    Stage3Settings,
    Stage3StructuralMisalignmentError,
    Stage3VLMOrchestrator,
    Stage4HandoffPayload,
    VerifiedDamagedPart,
    VLMInspectionOutput,
    execute_with_jitter_retry,
)


# ==============================================================================
# Test Fixtures & Factories
# ==============================================================================

def make_dummy_catalogue(key: str = "front_bumper") -> OEMPartCatalogueRecord:
    """Generate a valid OEM catalogue record for testing."""
    return OEMPartCatalogueRecord(
        canonical_part_key=key,
        display_part_name=key.replace("_", " ").title(),
        oem_part_number=f"OEM-{key.upper()}-999",
        part_material="PLASTIC" if "bumper" in key else "STEEL",
        depreciation_rate_non_zero_dep=0.10,
        oem_part_cost_inr=8500.0,
        rr_labour_inr=1200.0,
        denting_base_labour_inr=1500.0,
        full_panel_paint_inr=4500.0,
        pdr_or_polish_flat_inr=1800.0,
        is_repairable=True,
        is_safety_critical=False,
    )


def make_grounded_part(
    canonical_key: str,
    damage_class: str = "scratch",
    iop_ratio: float = 0.08,
    som_path: Optional[Path] = None,
    raw_path: Optional[Path] = None,
    is_claimed: bool = True,
) -> GroundedDamagedPart:
    """Generate a valid GroundedDamagedPart instance for testing."""
    cat = make_dummy_catalogue(canonical_key)
    return GroundedDamagedPart(
        canonical_part_key=canonical_key,
        raw_detected_part_classes=[canonical_key],
        side_resolution_method="DETERMINISTIC_TAXONOMY",
        display_part_name=cat.display_part_name,
        oem_part_number=cat.oem_part_number,
        part_material=cat.part_material,
        is_repairable=cat.is_repairable,
        is_safety_critical=cat.is_safety_critical,
        detected_damage_classes=[damage_class],
        primary_damage_class=damage_class,
        final_iop_ratio=iop_ratio,
        iop_percentage=iop_ratio * 100.0,
        iop_estimation_method="STABLE_UNION",
        zoom_clipped_frames_filtered=0,
        persistence_frame_count=5,
        part_confidence=0.95,
        damage_confidence=0.92,
        area_measurement_keyframe="frame_001.jpg",
        vlm_closeup_keyframe="frame_002.jpg",
        som_annotated_crop_path=som_path or Path("/tmp/som_crop.jpg"),
        som_raw_crop_path=raw_path or Path("/tmp/raw_crop.jpg"),
        svg_overlay=SVGOverlayPayload("frame_001.jpg", "0 0 1920 1080", [], []),
        catalogue_record=cat,
        is_claimed=is_claimed,
        claim_status="CLAIMED" if is_claimed else "UNCLAIMED",
    )


# ==============================================================================
# 1. DepthGrade Matrix ($L_1 \dots L_5$) Tests
# ==============================================================================

class TestDepthGradeTaxonomy:
    """Verify depth grade taxonomy completeness, schema parsing, and forensic mapping."""

    def test_depth_grade_enum_completeness(self):
        expected_grades = {
            "L1_SURFACE_SCUFF",
            "L2_BASECOAT_SCRATCH",
            "L3_SHALLOW_DENT_PDR",
            "L4_CREASED_DENT",
            "L5_STRUCTURAL_TEAR",
        }
        actual_grades = {g.value for g in DepthGrade}
        assert actual_grades == expected_grades

    @pytest.mark.parametrize("grade", list(DepthGrade))
    def test_vlm_inspection_output_depth_grades(self, grade: DepthGrade):
        output = VLMInspectionOutput(
            is_real_physical_damage=True,
            false_positive_reason=FalsePositiveReason.NONE,
            depth_grade=grade,
            has_rust_or_oxidation=False,
            has_panel_gap_misalignment=False,
            confidence=0.95,
            visual_reasoning_short=f"Tested depth grade {grade.value}",
        )
        assert output.depth_grade == grade
        assert output.is_real_physical_damage is True

    @pytest.mark.parametrize("grade", list(DepthGrade))
    def test_forensic_engine_maps_all_depth_grades(self, grade: DepthGrade):
        engine = ForensicDecisionEngine()
        part = make_grounded_part("front_fender", "dent", iop_ratio=0.07)
        vlm_output = VLMInspectionOutput(
            is_real_physical_damage=True,
            false_positive_reason=FalsePositiveReason.NONE,
            depth_grade=grade,
            has_rust_or_oxidation=False,
            has_panel_gap_misalignment=False,
            confidence=0.96,
            visual_reasoning_short=f"Classified as {grade.value}",
        )
        result = engine.validate_inspection_result(part, vlm_output, latency_ms=45.0)
        assert isinstance(result, VerifiedDamagedPart)
        assert result.depth_grade == grade
        assert result.canonical_part_key == "front_fender"
        assert result.is_real_physical_damage is True

    def test_forensic_engine_invalid_depth_grade_raises_malformed(self):
        engine = ForensicDecisionEngine()
        part = make_grounded_part("front_door", "scratch")
        vlm_output = VLMInspectionOutput(
            is_real_physical_damage=True,
            false_positive_reason=FalsePositiveReason.NONE,
            depth_grade=DepthGrade.L1_SURFACE_SCUFF,
            has_rust_or_oxidation=False,
            has_panel_gap_misalignment=False,
            confidence=0.90,
            visual_reasoning_short="Valid test output",
        )
        # Force bypass pydantic validation to verify forensic engine guard
        object.__setattr__(vlm_output, "depth_grade", "L6_NON_EXISTENT")
        with pytest.raises(Stage3MalformedOutputError) as exc_info:
            engine.validate_inspection_result(part, vlm_output)
        assert "Invalid depth grade" in str(exc_info.value)


# ==============================================================================
# 2. FalsePositiveReason Quarantine Matrix Tests
# ==============================================================================

class TestFalsePositiveQuarantineMatrix:
    """Verify that all superficial contaminant types drop into quarantined_parts."""

    ALL_FP_REASONS = [r for r in FalsePositiveReason if r != FalsePositiveReason.NONE]

    @pytest.mark.parametrize("fp_reason", ALL_FP_REASONS)
    def test_every_false_positive_reason_quarantines_part(self, fp_reason: FalsePositiveReason):
        engine = ForensicDecisionEngine()
        part = make_grounded_part("rear_door", "scratch")
        vlm_output = VLMInspectionOutput(
            is_real_physical_damage=False,
            false_positive_reason=fp_reason,
            depth_grade=DepthGrade.L1_SURFACE_SCUFF,
            has_rust_or_oxidation=False,
            has_panel_gap_misalignment=False,
            confidence=0.94,
            visual_reasoning_short=f"Identified {fp_reason.value} contaminant on clearcoat.",
        )

        decision = engine.validate_inspection_result(part, vlm_output, latency_ms=50.0)
        assert isinstance(decision, QuarantinedPartRecord)
        assert decision.canonical_part_key == "rear_door"
        assert decision.false_positive_reason == fp_reason
        assert decision.vlm_confidence == 0.94
        assert decision.visual_reasoning_short == f"Identified {fp_reason.value} contaminant on clearcoat."

    def test_false_positive_reason_none_coerced_to_other_non_damage(self):
        """When is_real_physical_damage=False but reason is NONE, engine coerces to OTHER_NON_DAMAGE."""
        engine = ForensicDecisionEngine()
        part = make_grounded_part("bonnet", "scratch")
        vlm_output = VLMInspectionOutput(
            is_real_physical_damage=False,
            false_positive_reason=FalsePositiveReason.NONE,
            depth_grade=DepthGrade.L1_SURFACE_SCUFF,
            has_rust_or_oxidation=False,
            has_panel_gap_misalignment=False,
            confidence=0.91,
            visual_reasoning_short="Generic non-physical reflection mark.",
        )

        decision = engine.validate_inspection_result(part, vlm_output)
        assert isinstance(decision, QuarantinedPartRecord)
        assert decision.false_positive_reason == FalsePositiveReason.OTHER_NON_DAMAGE

    @pytest.mark.asyncio
    async def test_orchestrator_quarantined_parts_excluded_from_verified_billing(self):
        """Verify orchestrator splits verified vs quarantined parts without billing false positives."""
        adapter = DeterministicMockVLMAdapter()
        orchestrator = Stage3VLMOrchestrator(adapter=adapter)

        claim_id = uuid4()
        real_part = make_grounded_part("front_bumper", "scratch", iop_ratio=0.05)
        dirt_part = make_grounded_part("bonnet", "scratch", som_path=Path("/tmp/dirt_crop.jpg"))
        bird_part = make_grounded_part("windshield", "dirt", som_path=Path("/tmp/bird_crop.jpg"))

        handoff = Stage3HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-TEST-001",
            registration_number="MH14CD5678",
            make="Tata",
            model="Harrier",
            grounded_parts=[real_part, dirt_part, bird_part],
            telemetry={},
        )

        payload: Stage4HandoffPayload = await orchestrator.inspect_claim(handoff)

        assert len(payload.verified_parts) == 1
        assert payload.verified_parts[0].canonical_part_key == "front_bumper"
        assert payload.verified_parts[0].depth_grade == DepthGrade.L2_BASECOAT_SCRATCH

        assert len(payload.quarantined_parts) == 2
        quarantined_keys = {q.canonical_part_key for q in payload.quarantined_parts}
        assert quarantined_keys == {"bonnet", "windshield"}
        assert payload.dismissed_parts == payload.quarantined_parts


# ==============================================================================
# 3. Rust / Oxidation Fraud Gate (ESC-04) Tests
# ==============================================================================

class TestRustOxidationFraudGateESC04:
    """Verify that detected rust/corrosion halts the pipeline and raises ESC-04."""

    def test_forensic_engine_rust_fraud_gate_attributes(self):
        engine = ForensicDecisionEngine()
        part = make_grounded_part("fender_left", "scratch", som_path=Path("/tmp/rust_evidence.jpg"))
        vlm_output = VLMInspectionOutput(
            is_real_physical_damage=True,
            false_positive_reason=FalsePositiveReason.NONE,
            depth_grade=DepthGrade.L2_BASECOAT_SCRATCH,
            has_rust_or_oxidation=True,
            rust_details="Heavy reddish-brown Fe2O3 oxidation flaking in scratch groove.",
            has_panel_gap_misalignment=False,
            confidence=0.98,
            visual_reasoning_short="Aged corrosion indicates pre-existing loss.",
        )

        with pytest.raises(Stage3RustOrOxidationError) as exc_info:
            engine.validate_inspection_result(part, vlm_output, claim_id="claim-rust-999")

        err = exc_info.value
        assert err.escalation_code == "ESC-04"
        assert err.failure_code == "ESC_04_PREEXISTING_CORROSION"
        assert err.part_key == "fender_left"
        assert err.claim_id == "claim-rust-999"
        assert err.evidence_path == Path("/tmp/rust_evidence.jpg")
        assert "Fe2O3 oxidation" in str(err)

    @pytest.mark.asyncio
    async def test_orchestrator_rust_halts_execution_immediately(self):
        adapter = DeterministicMockVLMAdapter()
        orchestrator = Stage3VLMOrchestrator(adapter=adapter)

        claim_id = uuid4()
        part = make_grounded_part("front_door", "scratch", som_path=Path("/tmp/rust_panel.jpg"))
        handoff = Stage3HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-RUST-01",
            registration_number="KA01AA1111",
            make="Hyundai",
            model="Verna",
            grounded_parts=[part],
            telemetry={},
        )

        with pytest.raises(Stage3RustOrOxidationError) as exc_info:
            await orchestrator.inspect_claim(handoff)

        assert exc_info.value.escalation_code == "ESC-04"
        assert exc_info.value.failure_code == Stage3FailureCode.ESC_04_PREEXISTING_CORROSION


# ==============================================================================
# 4. Structural Misalignment Safety Gate (ESC-06) Tests
# ==============================================================================

class TestStructuralMisalignmentSafetyGateESC06:
    """Verify that panel gap misalignment halts the pipeline and raises ESC-06."""

    def test_forensic_engine_structural_misalignment_gate_attributes(self):
        engine = ForensicDecisionEngine()
        part = make_grounded_part("front_left_door", "dent", som_path=Path("/tmp/misaligned_seam.jpg"))
        vlm_output = VLMInspectionOutput(
            is_real_physical_damage=True,
            false_positive_reason=FalsePositiveReason.NONE,
            depth_grade=DepthGrade.L4_CREASED_DENT,
            has_rust_or_oxidation=False,
            has_panel_gap_misalignment=True,
            misalignment_details="A-pillar distortion causes 8mm gap taper to 0mm wedging at sill.",
            confidence=0.97,
            visual_reasoning_short="Pillar collapse causes door binding.",
        )

        with pytest.raises(Stage3StructuralMisalignmentError) as exc_info:
            engine.validate_inspection_result(part, vlm_output, claim_id="claim-frame-001")

        err = exc_info.value
        assert err.escalation_code == "ESC-06"
        assert err.failure_code == "ESC_06_STRUCTURAL_HAZARD"
        assert err.part_key == "front_left_door"
        assert err.claim_id == "claim-frame-001"
        assert err.evidence_path == Path("/tmp/misaligned_seam.jpg")
        assert "A-pillar distortion" in str(err)

    @pytest.mark.asyncio
    async def test_orchestrator_misalignment_halts_execution_immediately(self):
        adapter = DeterministicMockVLMAdapter()
        orchestrator = Stage3VLMOrchestrator(adapter=adapter)

        claim_id = uuid4()
        part = make_grounded_part("front_left_door", "dent", som_path=Path("/tmp/gap_misalign.jpg"))
        handoff = Stage3HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-FRAME-02",
            registration_number="MH01ZZ0002",
            make="Mahindra",
            model="Scorpio-N",
            grounded_parts=[part],
            telemetry={},
        )

        with pytest.raises(Stage3StructuralMisalignmentError) as exc_info:
            await orchestrator.inspect_claim(handoff)

        assert exc_info.value.escalation_code == "ESC-06"
        assert exc_info.value.failure_code == Stage3FailureCode.ESC_06_STRUCTURAL_HAZARD

    def test_gate_precedence_rust_over_misalignment(self):
        """Rust fraud gate (Gate 1) takes precedence over frame misalignment (Gate 2)."""
        engine = ForensicDecisionEngine()
        part = make_grounded_part("bonnet", "dent")
        vlm_output = VLMInspectionOutput(
            is_real_physical_damage=True,
            false_positive_reason=FalsePositiveReason.NONE,
            depth_grade=DepthGrade.L4_CREASED_DENT,
            has_rust_or_oxidation=True,
            rust_details="Corroded hinge assembly.",
            has_panel_gap_misalignment=True,
            misalignment_details="Uneven hood margin.",
            confidence=0.99,
            visual_reasoning_short="Both rust and gap issue present.",
        )

        with pytest.raises(Stage3RustOrOxidationError) as exc_info:
            engine.validate_inspection_result(part, vlm_output)
        assert exc_info.value.escalation_code == "ESC-04"


# ==============================================================================
# 5. Zero Real Damage Gate (ESC-07) Tests
# ==============================================================================

class TestZeroRealDamageGateESC07:
    """Verify that when all claimed parts are false positives, ESC-07 is raised."""

    @pytest.mark.asyncio
    async def test_orchestrator_zero_real_damage_raises_esc07(self):
        adapter = DeterministicMockVLMAdapter()
        orchestrator = Stage3VLMOrchestrator(adapter=adapter)

        claim_id = uuid4()
        p1 = make_grounded_part("bonnet", "scratch", som_path=Path("/tmp/dirt_crop.jpg"))
        p2 = make_grounded_part("front_bumper", "scratch", som_path=Path("/tmp/glare_crop.jpg"))
        p3 = make_grounded_part("roof", "scratch", som_path=Path("/tmp/bird_crop.jpg"))

        handoff = Stage3HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-ESC07-01",
            registration_number="DL08AB1234",
            make="Maruti",
            model="Baleno",
            grounded_parts=[p1, p2, p3],
            telemetry={},
        )

        with pytest.raises(Stage3NoRealDamageDetectedError) as exc_info:
            await orchestrator.inspect_claim(handoff)

        err = exc_info.value
        assert err.escalation_code == "ESC-07"
        assert err.failure_code == "ESC_07_NO_REAL_DAMAGE_DETECTED"
        assert err.claim_id == claim_id
        assert len(err.dismissed_summary) == 3

        summary_keys = {item["canonical_part_key"] for item in err.dismissed_summary}
        assert summary_keys == {"bonnet", "front_bumper", "roof"}
        for item in err.dismissed_summary:
            assert "false_positive_reason" in item
            assert "visual_reasoning" in item
            assert "vlm_confidence" in item

    @pytest.mark.asyncio
    async def test_orchestrator_mixed_damage_does_not_raise_esc07(self):
        """Mixed claim with at least one verified part must not trigger ESC-07."""
        adapter = DeterministicMockVLMAdapter()
        orchestrator = Stage3VLMOrchestrator(adapter=adapter)

        claim_id = uuid4()
        p1_fake = make_grounded_part("bonnet", "scratch", som_path=Path("/tmp/dirt_crop.jpg"))
        p2_real = make_grounded_part("front_bumper", "dent", iop_ratio=0.06)

        handoff = Stage3HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-ESC07-02",
            registration_number="DL08AB5678",
            make="Maruti",
            model="Baleno",
            grounded_parts=[p1_fake, p2_real],
            telemetry={},
        )

        payload = await orchestrator.inspect_claim(handoff)
        assert len(payload.verified_parts) == 1
        assert len(payload.quarantined_parts) == 1
        assert payload.verified_parts[0].canonical_part_key == "front_bumper"


# ==============================================================================
# 6. CircuitBreaker State Machine & Retry Policy Tests
# ==============================================================================

class TestCircuitBreakerAndRetryPolicy:
    """Verify 5-strike tripping, cooldown window, and HALF_OPEN probe recovery."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_closed_to_open_after_5_failures(self):
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
        assert breaker.state == "CLOSED"

        async def failing_call():
            raise httpx.ConnectError("Connection refused")

        # First 4 failures increment counter but stay CLOSED
        for i in range(1, 5):
            with pytest.raises(httpx.ConnectError):
                await breaker.call(failing_call)
            assert breaker.failure_count == i
            assert breaker.state == "CLOSED"

        # 5th failure trips breaker to OPEN
        with pytest.raises(httpx.ConnectError):
            await breaker.call(failing_call)
        assert breaker.failure_count == 5
        assert breaker.state == "OPEN"

        # Subsequent call fails immediately with Stage3CircuitBreakerOpenError without calling func
        called = False
        async def dummy():
            nonlocal called
            called = True
            return "ok"

        with pytest.raises(Stage3CircuitBreakerOpenError) as exc_info:
            await breaker.call(dummy)
        assert not called
        assert "Circuit Breaker is OPEN" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery_to_half_open_and_closed(self):
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=0.05)

        async def failing_call():
            raise RuntimeError("simulated error")

        # Trip to OPEN
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call(failing_call)
        assert breaker.state == "OPEN"

        # Wait for recovery timeout to elapse
        await asyncio.sleep(0.06)

        # Next call transitions to HALF_OPEN and, on success, resets to CLOSED
        async def success_call():
            return "recovered_data"

        result = await breaker.call(success_call)
        assert result == "recovered_data"
        assert breaker.state == "CLOSED"
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_failure_re_trips_to_open(self):
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)

        async def failing_call():
            raise RuntimeError("err")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await breaker.call(failing_call)
        assert breaker.state == "OPEN"

        await asyncio.sleep(0.06)

        # Failure during HALF_OPEN immediately re-trips to OPEN
        with pytest.raises(RuntimeError):
            await breaker.call(failing_call)
        assert breaker.state == "OPEN"

    def test_circuit_breaker_manual_reset(self):
        breaker = CircuitBreaker(failure_threshold=2)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == "OPEN"

        breaker.reset()
        assert breaker.state == "CLOSED"
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_execute_with_jitter_retry_success_after_transient_failure(self):
        attempts = 0

        async def transient_func():
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise httpx.ReadTimeout("Timeout")
            return "success_val"

        result = await execute_with_jitter_retry(
            transient_func,
            max_retries=2,
            base_delays=(0.01, 0.02),
        )
        assert result == "success_val"
        assert attempts == 2

    @pytest.mark.asyncio
    async def test_execute_with_jitter_retry_exhaustion_raises(self):
        attempts = 0

        async def permanently_failing():
            nonlocal attempts
            attempts += 1
            raise ValueError("Persistent fault")

        with pytest.raises(ValueError) as exc_info:
            await execute_with_jitter_retry(
                permanently_failing,
                max_retries=2,
                base_delays=(0.01, 0.02),
            )
        assert "Persistent fault" in str(exc_info.value)
        assert attempts == 3


# ==============================================================================
# 7. ResilientJSONParser Edge Cases
# ==============================================================================

class TestResilientJSONParserEdgeCases:
    """Verify markdown stripping, trailing comma repair, Python dict normalization."""

    def test_clean_json_string_with_standard_code_fences(self):
        raw = '```json\n{"key": "value"}\n```'
        cleaned = ResilientJSONParser.clean_json_string(raw)
        assert json.loads(cleaned) == {"key": "value"}

    def test_clean_json_string_with_generic_code_fences(self):
        raw = '```\n{"score": 42}\n```'
        cleaned = ResilientJSONParser.clean_json_string(raw)
        assert json.loads(cleaned) == {"score": 42}

    def test_clean_json_string_with_conversational_text(self):
        raw = (
            "Based on forensic visual cross-examination of Image 1 and Image 2, here is the output:\n\n"
            '{"is_real_physical_damage": true, "depth_grade": "L2_BASECOAT_SCRATCH"}\n\n'
            "Hope this inspection analysis assists your claims evaluation."
        )
        cleaned = ResilientJSONParser.clean_json_string(raw)
        data = json.loads(cleaned)
        assert data["is_real_physical_damage"] is True
        assert data["depth_grade"] == "L2_BASECOAT_SCRATCH"

    def test_clean_json_string_trailing_commas_in_objects_and_arrays(self):
        raw = '{"name": "test", "items": [1, 2, 3,], "details": {"active": true,},}'
        cleaned = ResilientJSONParser.clean_json_string(raw)
        data = json.loads(cleaned)
        assert data == {"name": "test", "items": [1, 2, 3], "details": {"active": True}}

    def test_parse_and_validate_with_python_literals(self):
        raw = """
        {
            'is_real_physical_damage': True,
            'false_positive_reason': 'NONE',
            'depth_grade': 'L3_SHALLOW_DENT_PDR',
            'has_rust_or_oxidation': False,
            'rust_details': None,
            'has_panel_gap_misalignment': False,
            'misalignment_details': None,
            'confidence': 0.95,
            'visual_reasoning_short': 'Smooth dent without crease.',
        }
        """.replace("'", '"')

        parsed = ResilientJSONParser.parse_and_validate(raw, VLMInspectionOutput)
        assert parsed.is_real_physical_damage is True
        assert parsed.depth_grade == DepthGrade.L3_SHALLOW_DENT_PDR
        assert parsed.rust_details is None
        assert parsed.confidence == 0.95

    def test_parse_and_validate_empty_string_raises(self):
        with pytest.raises(Stage3MalformedOutputError) as exc_info:
            ResilientJSONParser.parse_and_validate("", VLMInspectionOutput)
        assert "output is empty" in str(exc_info.value)

        with pytest.raises(Stage3MalformedOutputError):
            ResilientJSONParser.parse_and_validate("    \n\t  ", VLMInspectionOutput)

    def test_parse_and_validate_unrecoverable_json_raises(self):
        raw = "Sorry, I am an AI and cannot process image crops without metadata."
        with pytest.raises(Stage3MalformedOutputError) as exc_info:
            ResilientJSONParser.parse_and_validate(raw, VLMInspectionOutput)
        assert "Failed to decode JSON" in str(exc_info.value)
        assert exc_info.value.raw_output == raw

    def test_parse_and_validate_schema_mismatch_raises(self):
        # Missing required field 'depth_grade' and 'confidence'
        raw = '{"is_real_physical_damage": true, "visual_reasoning_short": "Scuff"}'
        with pytest.raises(Stage3MalformedOutputError) as exc_info:
            ResilientJSONParser.parse_and_validate(raw, VLMInspectionOutput)
        assert "Validation error against VLMInspectionOutput" in str(exc_info.value)


# ==============================================================================
# 8. End-to-End Pipeline Bridge (Stage 2 -> Stage 3 -> Stage 4)
# ==============================================================================

class TestEndToEndPipelineBridge:
    """Verify complete contract conformance between Stage 2 handoff and Stage 4 payload."""

    @pytest.mark.asyncio
    async def test_full_stage2_to_stage4_bridge_contract(self, tmp_path: Path):
        # 1. Prepare dummy crop files
        som_img = tmp_path / "crop_som.jpg"
        raw_img = tmp_path / "crop_raw.jpg"
        som_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
        raw_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)

        # 2. Prepare 3 candidate parts
        p_real = make_grounded_part("front_bumper", "scratch", iop_ratio=0.05, som_path=som_img, raw_path=raw_img)
        p_dirt = make_grounded_part("bonnet", "scratch", som_path=Path("/tmp/dirt_spot.jpg"), raw_path=raw_img)
        p_unclaimed = make_grounded_part("back_door", "dent", is_claimed=False, som_path=som_img, raw_path=raw_img)

        claim_id = uuid4()
        stage2_handoff = Stage3HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-STAGE2-BRIDGE-99",
            registration_number="MH12XY0007",
            make="Mahindra",
            model="XUV700",
            grounded_parts=[p_real, p_dirt, p_unclaimed],
            telemetry={"stage2_latency_ms": 420.0, "keyframe_count": 12},
            claim_intent="FRONT_ACCIDENT",
        )

        adapter = DeterministicMockVLMAdapter()
        orchestrator = Stage3VLMOrchestrator(adapter=adapter)

        # 3. Execute inspection
        stage4_payload: Stage4HandoffPayload = await orchestrator.inspect_claim(stage2_handoff)

        # 4. Strict assertion against Stage4HandoffPayload schema
        assert isinstance(stage4_payload, Stage4HandoffPayload)
        assert stage4_payload.claim_id == claim_id
        assert stage4_payload.policy_id == "POL-STAGE2-BRIDGE-99"
        assert stage4_payload.registration_number == "MH12XY0007"
        assert stage4_payload.make == "Mahindra"
        assert stage4_payload.model == "XUV700"
        assert stage4_payload.claim_intent == "FRONT_ACCIDENT"

        # Exactly 1 verified part
        assert len(stage4_payload.verified_parts) == 1
        verified = stage4_payload.verified_parts[0]
        assert verified.canonical_part_key == "front_bumper"
        assert verified.depth_grade == DepthGrade.L2_BASECOAT_SCRATCH
        assert verified.is_real_physical_damage is True
        assert verified.catalogue_record is not None
        assert verified.catalogue_record.oem_part_cost_inr == 8500.0

        # Exactly 2 quarantined parts (1 dirt false positive + 1 unclaimed)
        assert len(stage4_payload.quarantined_parts) == 2
        quarantined_keys = [q.canonical_part_key for q in stage4_payload.quarantined_parts]
        assert "bonnet" in quarantined_keys
        assert "back_door" in quarantined_keys

        # Upstream and downstream telemetry merging
        tel = stage4_payload.telemetry
        assert tel["stage2_latency_ms"] == 420.0
        assert "stage3_telemetry" in tel
        s3_tel = tel["stage3_telemetry"]
        assert s3_tel["parts_inspected_count"] == 3
        assert s3_tel["parts_verified_count"] == 1
        assert s3_tel["parts_quarantined_count"] == 2
        assert s3_tel["status"] == "S3_PASSED"
        assert s3_tel["total_latency_ms"] >= 0.0

