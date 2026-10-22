"""Comprehensive tests for Stage 3 VLM Damage Inspection Orchestrator, Forensic Engine, and Prompt Engine."""

from __future__ import annotations

from pathlib import Path
from typing import List
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.domain.dual_mask_segmentation.schemas import (
    GroundedDamagedPart,
    OEMPartCatalogueRecord,
    Stage3HandoffPayload,
    SVGOverlayPayload,
)
from app.domain.vlm_damage_inspection.adapters.mock_adapter import DeterministicMockVLMAdapter
from app.domain.vlm_damage_inspection.config import Stage3Settings
from app.domain.vlm_damage_inspection.exceptions import (
    Stage3MalformedOutputError,
    Stage3NoRealDamageDetectedError,
    Stage3RustOrOxidationError,
    Stage3StructuralMisalignmentError,
)
from app.domain.vlm_damage_inspection.forensic_engine import ForensicDecisionEngine
from app.domain.vlm_damage_inspection.orchestrator import Stage3VLMOrchestrator
from app.domain.vlm_damage_inspection.prompt_engine import VLMPromptEngine
from app.domain.vlm_damage_inspection.schemas import (
    DepthGrade,
    FalsePositiveReason,
    HarnessAction,
    InspectionContext,
    QuarantinedPartRecord,
    Stage4HandoffPayload,
    VehicleOrientation,
    VerifiedDamagedPart,
    VLMInspectionOutput,
)


def _make_dummy_catalogue_record(key: str = "front_bumper") -> OEMPartCatalogueRecord:
    return OEMPartCatalogueRecord(
        canonical_part_key=key,
        display_part_name=key.replace("_", " ").title(),
        oem_part_number=f"OEM-{key.upper()}-001",
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


def _make_grounded_part(
    canonical_key: str,
    damage_class: str = "scratch",
    iop_ratio: float = 0.08,
    som_path: str = "/tmp/crop_som.jpg",
    raw_path: str = "/tmp/crop_raw.jpg",
    is_claimed: bool = True,
) -> GroundedDamagedPart:
    catalogue = _make_dummy_catalogue_record(canonical_key)
    return GroundedDamagedPart(
        canonical_part_key=canonical_key,
        raw_detected_part_classes=[canonical_key],
        side_resolution_method="DETERMINISTIC_TAXONOMY",
        display_part_name=catalogue.display_part_name,
        oem_part_number=catalogue.oem_part_number,
        part_material=catalogue.part_material,
        is_repairable=catalogue.is_repairable,
        is_safety_critical=catalogue.is_safety_critical,
        detected_damage_classes=[damage_class],
        primary_damage_class=damage_class,
        final_iop_ratio=iop_ratio,
        iop_percentage=iop_ratio * 100.0,
        iop_estimation_method="STABLE_UNION",
        zoom_clipped_frames_filtered=0,
        persistence_frame_count=5,
        part_confidence=0.92,
        damage_confidence=0.89,
        area_measurement_keyframe="frame_001.jpg",
        vlm_closeup_keyframe="frame_002.jpg",
        som_annotated_crop_path=Path(som_path),
        som_raw_crop_path=Path(raw_path),
        svg_overlay=SVGOverlayPayload("frame_001.jpg", "0 0 1920 1080", [], []),
        catalogue_record=catalogue,
        is_claimed=is_claimed,
        claim_status="CLAIMED" if is_claimed else "UNCLAIMED",
    )


# ==============================================================================
# 1. VLMPromptEngine Tests
# ==============================================================================


def test_prompt_engine_system_prompt():
    engine = VLMPromptEngine()
    assert "Chief Automotive Forensics" in engine.system_prompt
    assert "PHYSICAL OBJECTIVITY" in engine.system_prompt
    assert "ESC-04" in engine.system_prompt
    assert "ESC-06" in engine.system_prompt


def test_prompt_engine_build_inspection_prompt():
    ctx = InspectionContext(
        canonical_part_key="front_bumper",
        part_display_name="Front Bumper",
        primary_damage_class="scratch",
        make="Hyundai",
        model="Creta",
        iop_ratio=0.075,
    )
    prompt = VLMPromptEngine.build_inspection_prompt(ctx)
    assert "Hyundai Creta" in prompt
    assert "Front Bumper" in prompt
    assert "canonical_key: front_bumper" in prompt
    assert "7.5%" in prompt
    assert "Image 1 (Set-of-Marks)" in prompt
    assert "Image 2 (Raw Crop)" in prompt
    assert "ESC-04: Pre-Existing Rust" in prompt
    assert "ESC-06: Structural Frame Misalignment" in prompt
    assert "VLMInspectionOutput" in prompt


# ==============================================================================
# 2. ForensicDecisionEngine Tests
# ==============================================================================


def test_forensic_engine_verified_part_success():
    engine = ForensicDecisionEngine()
    part = _make_grounded_part("front_bumper", "dent", iop_ratio=0.06)
    vlm_output = VLMInspectionOutput(
        is_real_physical_damage=True,
        false_positive_reason=FalsePositiveReason.NONE,
        depth_grade=DepthGrade.L3_SHALLOW_DENT_PDR,
        has_rust_or_oxidation=False,
        has_panel_gap_misalignment=False,
        confidence=0.95,
        visual_reasoning_short="Smooth concave depression with clearcoat intact.",
    )

    result = engine.validate_inspection_result(part, vlm_output, latency_ms=120.0)
    assert isinstance(result, VerifiedDamagedPart)
    assert result.canonical_part_key == "front_bumper"
    assert result.depth_grade == DepthGrade.L3_SHALLOW_DENT_PDR
    assert result.vlm_confidence == 0.95
    assert result.visual_reasoning_short == "Smooth concave depression with clearcoat intact."
    assert result.latency_ms == 120.0
    assert result.is_real_physical_damage is True


def test_forensic_engine_rust_fraud_gate_esc04():
    engine = ForensicDecisionEngine()
    part = _make_grounded_part("front_left_fender", "scratch", som_path="/tmp/rust_crop.jpg")
    vlm_output = VLMInspectionOutput(
        is_real_physical_damage=True,
        false_positive_reason=FalsePositiveReason.NONE,
        depth_grade=DepthGrade.L2_BASECOAT_SCRATCH,
        has_rust_or_oxidation=True,
        rust_details="Reddish-brown iron oxide flaking inside deep scratch groove.",
        has_panel_gap_misalignment=False,
        confidence=0.97,
        visual_reasoning_short="Oxidized metal substrate indicating aged damage.",
    )

    with pytest.raises(Stage3RustOrOxidationError) as exc_info:
        engine.validate_inspection_result(part, vlm_output)

    err = exc_info.value
    assert err.escalation_code == "ESC-04"
    assert err.failure_code == "ESC_04_PREEXISTING_CORROSION"
    assert err.part_key == "front_left_fender"
    assert "Pre-existing rust/oxidation detected on front_left_fender" in str(err)


def test_forensic_engine_frame_misalignment_gate_esc06():
    engine = ForensicDecisionEngine()
    part = _make_grounded_part("front_left_door", "dent", som_path="/tmp/misaligned_door.jpg")
    vlm_output = VLMInspectionOutput(
        is_real_physical_damage=True,
        false_positive_reason=FalsePositiveReason.NONE,
        depth_grade=DepthGrade.L4_CREASED_DENT,
        has_rust_or_oxidation=False,
        has_panel_gap_misalignment=True,
        misalignment_details="Door-to-fender seam pinched from 7mm at cowl to 0mm at lower sill.",
        confidence=0.96,
        visual_reasoning_short="Pillar distortion causing severe panel gap taper.",
    )

    with pytest.raises(Stage3StructuralMisalignmentError) as exc_info:
        engine.validate_inspection_result(part, vlm_output)

    err = exc_info.value
    assert err.escalation_code == "ESC-06"
    assert err.failure_code == "ESC_06_STRUCTURAL_HAZARD"
    assert err.part_key == "front_left_door"
    assert "Panel gap misalignment detected on front_left_door" in str(err)


def test_forensic_engine_false_positive_quarantine():
    engine = ForensicDecisionEngine()
    part = _make_grounded_part("bonnet", "scratch", som_path="/tmp/dirt_crop.jpg")
    vlm_output = VLMInspectionOutput(
        is_real_physical_damage=False,
        false_positive_reason=FalsePositiveReason.MUD_OR_DIRT,
        depth_grade=DepthGrade.L1_SURFACE_SCUFF,
        has_rust_or_oxidation=False,
        has_panel_gap_misalignment=False,
        confidence=0.94,
        visual_reasoning_short="Surface mud clump resting above clearcoat.",
    )

    result = engine.validate_inspection_result(part, vlm_output, latency_ms=80.0)
    assert isinstance(result, QuarantinedPartRecord)
    assert result.canonical_part_key == "bonnet"
    assert result.false_positive_reason == FalsePositiveReason.MUD_OR_DIRT
    assert result.visual_reasoning_short == "Surface mud clump resting above clearcoat."
    assert result.vlm_confidence == 0.94
    assert result.latency_ms == 80.0


def test_forensic_engine_invalid_depth_grade_raises():
    engine = ForensicDecisionEngine()
    part = _make_grounded_part("bonnet", "scratch")
    vlm_output = VLMInspectionOutput(
        is_real_physical_damage=True,
        false_positive_reason=FalsePositiveReason.NONE,
        depth_grade=DepthGrade.L1_SURFACE_SCUFF,
        has_rust_or_oxidation=False,
        has_panel_gap_misalignment=False,
        confidence=0.90,
        visual_reasoning_short="Valid inspection.",
    )
    # Manually bypass pydantic validator to test engine guard
    object.__setattr__(vlm_output, "depth_grade", "INVALID_GRADE")

    with pytest.raises(Stage3MalformedOutputError) as exc_info:
        engine.validate_inspection_result(part, vlm_output)

    assert "Invalid depth grade" in str(exc_info.value)


# ==============================================================================
# 3. Stage3VLMOrchestrator End-to-End Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_orchestrator_single_part_verified():
    adapter = DeterministicMockVLMAdapter()
    orchestrator = Stage3VLMOrchestrator(adapter=adapter)

    claim_id = uuid4()
    part = _make_grounded_part("front_bumper", "scratch", iop_ratio=0.05)
    handoff = Stage3HandoffPayload(
        claim_id=claim_id,
        policy_id="POL-9921",
        registration_number="MH12AB1234",
        make="Hyundai",
        model="Creta",
        grounded_parts=[part],
        telemetry={"stage2_latency_ms": 350.0},
    )

    payload: Stage4HandoffPayload = await orchestrator.inspect_claim(handoff)

    assert payload.claim_id == claim_id
    assert payload.policy_id == "POL-9921"
    assert payload.registration_number == "MH12AB1234"
    assert payload.make == "Hyundai"
    assert payload.model == "Creta"
    assert len(payload.verified_parts) == 1
    assert len(payload.quarantined_parts) == 0

    verified = payload.verified_parts[0]
    assert verified.canonical_part_key == "front_bumper"
    assert verified.depth_grade == DepthGrade.L2_BASECOAT_SCRATCH
    assert verified.is_real_physical_damage is True

    # Telemetry assertions
    assert "stage3_telemetry" in payload.telemetry
    s3_tel = payload.telemetry["stage3_telemetry"]
    assert s3_tel["parts_inspected_count"] == 1
    assert s3_tel["parts_verified_count"] == 1
    assert s3_tel["parts_quarantined_count"] == 0
    assert s3_tel["status"] == "S3_PASSED"


@pytest.mark.asyncio
async def test_orchestrator_quarantine_dirt_and_verify_real():
    adapter = DeterministicMockVLMAdapter()
    orchestrator = Stage3VLMOrchestrator(adapter=adapter)

    claim_id = uuid4()
    p1 = _make_grounded_part("front_bumper", "scratch", som_path="/tmp/dirt_crop.jpg")
    p2 = _make_grounded_part("front_left_door", "dent", som_path="/tmp/door_crop.jpg", iop_ratio=0.04)

    handoff = Stage3HandoffPayload(
        claim_id=claim_id,
        policy_id="POL-9922",
        registration_number="DL01XY9999",
        make="Maruti",
        model="Swift",
        grounded_parts=[p1, p2],
        telemetry={},
    )

    payload: Stage4HandoffPayload = await orchestrator.inspect_claim(handoff)

    assert len(payload.verified_parts) == 1
    assert len(payload.quarantined_parts) == 1

    # p1 should be quarantined as dirt
    quarantined = payload.quarantined_parts[0]
    assert quarantined.canonical_part_key == "front_bumper"
    assert quarantined.false_positive_reason == FalsePositiveReason.MUD_OR_DIRT

    # p2 should be verified as L3 dent
    verified = payload.verified_parts[0]
    assert verified.canonical_part_key == "front_left_door"
    assert verified.depth_grade == DepthGrade.L3_SHALLOW_DENT_PDR

    # Check dismissed_parts backward-compatibility property
    assert payload.dismissed_parts == payload.quarantined_parts


@pytest.mark.asyncio
async def test_orchestrator_unclaimed_part_quarantined():
    adapter = DeterministicMockVLMAdapter()
    orchestrator = Stage3VLMOrchestrator(adapter=adapter)

    claim_id = uuid4()
    p1 = _make_grounded_part("back_bumper", "scratch", is_claimed=False)
    p2 = _make_grounded_part("front_bumper", "scratch", is_claimed=True)

    handoff = Stage3HandoffPayload(
        claim_id=claim_id,
        policy_id="POL-9923",
        registration_number="KA03MG5555",
        make="Honda",
        model="City",
        grounded_parts=[p1, p2],
        telemetry={},
    )

    payload = await orchestrator.inspect_claim(handoff)
    assert len(payload.verified_parts) == 1
    assert len(payload.quarantined_parts) == 1
    assert payload.quarantined_parts[0].canonical_part_key == "back_bumper"
    assert "unclaimed" in payload.quarantined_parts[0].visual_reasoning_short


@pytest.mark.asyncio
async def test_orchestrator_zero_real_damage_esc07():
    adapter = DeterministicMockVLMAdapter()
    orchestrator = Stage3VLMOrchestrator(adapter=adapter)

    claim_id = uuid4()
    p1 = _make_grounded_part("front_bumper", "scratch", som_path="/tmp/dirt_crop.jpg")
    p2 = _make_grounded_part("bonnet", "scratch", som_path="/tmp/glare_crop.jpg")

    handoff = Stage3HandoffPayload(
        claim_id=claim_id,
        policy_id="POL-9924",
        registration_number="MH02CL1111",
        make="Tata",
        model="Nexon",
        grounded_parts=[p1, p2],
        telemetry={},
    )

    with pytest.raises(Stage3NoRealDamageDetectedError) as exc_info:
        await orchestrator.inspect_claim(handoff)

    err = exc_info.value
    assert err.escalation_code == "ESC-07"
    assert err.failure_code == "ESC_07_NO_REAL_DAMAGE_DETECTED"
    assert err.claim_id == claim_id
    assert len(err.dismissed_summary) == 2


@pytest.mark.asyncio
async def test_orchestrator_rust_escalation_halts_pipeline():
    adapter = DeterministicMockVLMAdapter()
    orchestrator = Stage3VLMOrchestrator(adapter=adapter)

    claim_id = uuid4()
    p1 = _make_grounded_part("front_fender", "scratch", som_path="/tmp/rust_damage.jpg")

    handoff = Stage3HandoffPayload(
        claim_id=claim_id,
        policy_id="POL-9925",
        registration_number="KA01HH2222",
        make="Kia",
        model="Seltos",
        grounded_parts=[p1],
        telemetry={},
    )

    with pytest.raises(Stage3RustOrOxidationError) as exc_info:
        await orchestrator.inspect_claim(handoff)

    assert exc_info.value.escalation_code == "ESC-04"
    assert exc_info.value.part_key == "front_fender"


@pytest.mark.asyncio
async def test_orchestrator_frame_misalignment_escalation():
    adapter = DeterministicMockVLMAdapter()
    orchestrator = Stage3VLMOrchestrator(adapter=adapter)

    claim_id = uuid4()
    p1 = _make_grounded_part("front_left_door", "dent", som_path="/tmp/frame_misaligned.jpg")

    handoff = Stage3HandoffPayload(
        claim_id=claim_id,
        policy_id="POL-9926",
        registration_number="UP16AA0001",
        make="Toyota",
        model="Innova",
        grounded_parts=[p1],
        telemetry={},
    )

    with pytest.raises(Stage3StructuralMisalignmentError) as exc_info:
        await orchestrator.inspect_claim(handoff)

    assert exc_info.value.escalation_code == "ESC-06"
    assert exc_info.value.part_key == "front_left_door"


@pytest.mark.asyncio
async def test_orchestrator_execute_alias_matches_inspect_claim():
    adapter = DeterministicMockVLMAdapter()
    orchestrator = Stage3VLMOrchestrator(adapter=adapter)

    claim_id = uuid4()
    part = _make_grounded_part("boot", "scratch")
    handoff = Stage3HandoffPayload(
        claim_id=claim_id,
        policy_id="POL-9927",
        registration_number="MH04XX8888",
        make="Mahindra",
        model="XUV700",
        grounded_parts=[part],
        telemetry={},
    )

    result_inspect = await orchestrator.inspect_claim(handoff)
    result_execute = await orchestrator.execute(handoff)

    assert result_inspect.claim_id == result_execute.claim_id
    assert len(result_inspect.verified_parts) == len(result_execute.verified_parts)
    assert result_inspect.verified_parts[0].canonical_part_key == result_execute.verified_parts[0].canonical_part_key


def test_prompt_engine_orientation_and_orchestrator_instructions():
    """Verify system prompt and user prompt contain vehicle orientation, component, and missing part instructions."""
    engine = VLMPromptEngine()
    prompt = engine.system_prompt
    assert "VEHICLE ORIENTATION" in prompt or "orientation" in prompt.lower()
    assert "COMPONENT-WISE" in prompt or "component" in prompt.lower()
    assert "duplicate" in prompt.lower()
    assert "missing" in prompt.lower()

    ctx = InspectionContext(
        canonical_part_key="front_bumper",
        part_display_name="Front Bumper",
        primary_damage_class="scratch",
        make="Hyundai",
        model="Creta",
        iop_ratio=0.08,
    )
    user_prompt = VLMPromptEngine.build_inspection_prompt(ctx)
    assert "vehicle_orientation" in user_prompt
    assert "component_matches_target" in user_prompt
    assert "possible_duplicate" in user_prompt
    assert "missing_parts_detected" in user_prompt


@pytest.mark.asyncio
async def test_orchestrator_deduplicates_repeating_damage_candidates():
    """Verify orchestrator filters out duplicate damage candidates so no duplicate parts are output to Stage 4."""
    adapter = DeterministicMockVLMAdapter()
    orchestrator = Stage3VLMOrchestrator(adapter=adapter)

    claim_id = uuid4()
    p1 = _make_grounded_part("front_bumper", "scratch", iop_ratio=0.08)
    p2 = _make_grounded_part("front_bumper_duplicate", "scratch", iop_ratio=0.07)

    async def mock_inspect_damage(som_crop_bytes, raw_crop_bytes, context):
        if context.canonical_part_key == "front_bumper_duplicate":
            return VLMInspectionOutput(
                is_real_physical_damage=True,
                depth_grade=DepthGrade.L2_BASECOAT_SCRATCH,
                confidence=0.88,
                visual_reasoning_short="Duplicate damage signature from adjacent crop.",
                possible_duplicate=True,
                duplicate_of_part_key="front_bumper",
            )
        return VLMInspectionOutput(
            is_real_physical_damage=True,
            depth_grade=DepthGrade.L2_BASECOAT_SCRATCH,
            confidence=0.95,
            visual_reasoning_short="Verified front bumper scratch.",
            possible_duplicate=False,
        )

    adapter.inspect_damage = AsyncMock(side_effect=mock_inspect_damage)

    handoff = Stage3HandoffPayload(
        claim_id=claim_id,
        policy_id="POL-DEDUP",
        registration_number="MH12DD0001",
        make="Hyundai",
        model="Creta",
        grounded_parts=[p1, p2],
        telemetry={},
    )

    payload = await orchestrator.inspect_claim(handoff)

    assert len(payload.verified_parts) == 1
    assert payload.verified_parts[0].canonical_part_key == "front_bumper"
    assert len(payload.quarantined_parts) == 1
    assert payload.quarantined_parts[0].canonical_part_key == "front_bumper_duplicate"
    assert "duplicate" in payload.quarantined_parts[0].visual_reasoning_short.lower()


@pytest.mark.asyncio
async def test_orchestrator_reidentification_loop_on_component_mismatch():
    """Verify orchestrator sends sub-crop to re-identification service when component mismatch is detected."""
    adapter = DeterministicMockVLMAdapter()

    reid_service = AsyncMock()
    reid_service.reidentify_component = AsyncMock(return_value="front_left_fender")

    orchestrator = Stage3VLMOrchestrator(
        adapter=adapter,
        reidentification_service=reid_service,
    )

    claim_id = uuid4()
    p1 = _make_grounded_part("front_bumper", "dent", iop_ratio=0.10)

    async def mock_inspect_damage(som_crop_bytes, raw_crop_bytes, context):
        return VLMInspectionOutput(
            is_real_physical_damage=True,
            depth_grade=DepthGrade.L3_SHALLOW_DENT_PDR,
            confidence=0.93,
            visual_reasoning_short="Damage is physically located on adjacent fender panel.",
            vehicle_orientation=VehicleOrientation.FRONT_LEFT_3_QUARTER,
            detected_component="front_left_fender",
            component_matches_target=False,
            needs_reidentification=True,
            reidentification_roi_bbox=[0.1, 0.2, 0.6, 0.8],
        )

    adapter.inspect_damage = AsyncMock(side_effect=mock_inspect_damage)

    handoff = Stage3HandoffPayload(
        claim_id=claim_id,
        policy_id="POL-REID",
        registration_number="KA05RE1111",
        make="Kia",
        model="Seltos",
        grounded_parts=[p1],
        telemetry={},
    )

    payload = await orchestrator.inspect_claim(handoff)

    reid_service.reidentify_component.assert_awaited_once()
    assert len(payload.verified_parts) == 1
    assert payload.verified_parts[0].canonical_part_key == "front_left_fender"


@pytest.mark.asyncio
async def test_orchestrator_telemetry_captures_missing_parts():
    """Verify missing parts detected across crops are aggregated and tracked in telemetry."""
    adapter = DeterministicMockVLMAdapter()
    orchestrator = Stage3VLMOrchestrator(adapter=adapter)

    claim_id = uuid4()
    p1 = _make_grounded_part("front_bumper", "tear", iop_ratio=0.15)

    async def mock_inspect_damage(som_crop_bytes, raw_crop_bytes, context):
        return VLMInspectionOutput(
            is_real_physical_damage=True,
            depth_grade=DepthGrade.L5_STRUCTURAL_TEAR,
            confidence=0.96,
            visual_reasoning_short="Bumper fascia fractured with fog lamp bezel missing.",
            vehicle_orientation=VehicleOrientation.FRONT,
            detected_component="front_bumper",
            component_matches_target=True,
            missing_parts_detected=["fog_lamp_bezel_left", "tow_eye_cap"],
        )

    adapter.inspect_damage = AsyncMock(side_effect=mock_inspect_damage)

    handoff = Stage3HandoffPayload(
        claim_id=claim_id,
        policy_id="POL-MISSING",
        registration_number="DL02MI2222",
        make="Toyota",
        model="Fortuner",
        grounded_parts=[p1],
        telemetry={},
    )

    payload = await orchestrator.inspect_claim(handoff)

    assert len(payload.verified_parts) == 1
    s3_telemetry = payload.telemetry.get("stage3_telemetry", {})
    assert "missing_parts_detected" in s3_telemetry
    assert "fog_lamp_bezel_left" in s3_telemetry["missing_parts_detected"]
    assert "tow_eye_cap" in s3_telemetry["missing_parts_detected"]


@pytest.mark.asyncio
async def test_orchestrator_harness_action_quarantine():
    """Verify harness_action=QUARANTINE immediately directs candidate to quarantined_parts."""
    adapter = DeterministicMockVLMAdapter()
    orchestrator = Stage3VLMOrchestrator(adapter=adapter)

    claim_id = uuid4()
    p1 = _make_grounded_part("hood", "scratch", iop_ratio=0.04)

    async def mock_inspect_damage(som_crop_bytes, raw_crop_bytes, context, full_frame_bytes=None):
        return VLMInspectionOutput(
            is_real_physical_damage=False,
            false_positive_reason=FalsePositiveReason.SPECULAR_GLARE,
            depth_grade=DepthGrade.L1_SURFACE_SCUFF,
            confidence=0.98,
            visual_reasoning_short="Optical sunlight reflection flare across bonnet curve.",
            vehicle_orientation=VehicleOrientation.FRONT,
            harness_action=HarnessAction.QUARANTINE,
            reextraction_reason="Optical flare confirmed from full frame angle.",
        )

    adapter.inspect_damage = AsyncMock(side_effect=mock_inspect_damage)

    handoff = Stage3HandoffPayload(
        claim_id=claim_id,
        policy_id="POL-QUARANTINE",
        registration_number="MH12QR9999",
        make="Hyundai",
        model="Creta",
        grounded_parts=[p1],
        telemetry={},
    )

    with pytest.raises(Stage3NoRealDamageDetectedError):
        await orchestrator.inspect_claim(handoff)


@pytest.mark.asyncio
async def test_orchestrator_dynamic_recrop_loop():
    """Verify harness_action=REQUEST_DYNAMIC_RECROP triggers dynamic cropping against full frame and re-inspection."""
    adapter = DeterministicMockVLMAdapter()
    orchestrator = Stage3VLMOrchestrator(adapter=adapter)

    claim_id = uuid4()
    p1 = _make_grounded_part("front_door", "dent", iop_ratio=0.12)
    # Give it mock full frame path
    p1.som_full_annotated_path = Path("/tmp/mock_full_frame.jpg")

    inspection_calls = 0

    async def mock_inspect_damage(som_crop_bytes, raw_crop_bytes, context, full_frame_bytes=None):
        nonlocal inspection_calls
        inspection_calls += 1
        if inspection_calls == 1:
            # First pass: harness judges crop is too tight, requests adaptive recrop
            return VLMInspectionOutput(
                is_real_physical_damage=True,
                depth_grade=DepthGrade.L3_SHALLOW_DENT_PDR,
                confidence=0.75,
                visual_reasoning_short="Initial crop cuts through door handle crease line.",
                vehicle_orientation=VehicleOrientation.LEFT_SIDE,
                detected_component="front_door",
                component_matches_target=True,
                harness_action=HarnessAction.REQUEST_DYNAMIC_RECROP,
                requested_crop_bbox=[0.1, 0.2, 0.8, 0.9],
                reextraction_reason="Re-extract wider window from full frame to verify complete dent perimeter.",
            )
        else:
            # Second pass: inspects the newly cut dynamic crop and passes
            return VLMInspectionOutput(
                is_real_physical_damage=True,
                depth_grade=DepthGrade.L4_CREASED_DENT,
                confidence=0.96,
                visual_reasoning_short="Adaptive recrop confirms deep creased dent extending across handle.",
                vehicle_orientation=VehicleOrientation.LEFT_SIDE,
                detected_component="front_door",
                component_matches_target=True,
                harness_action=HarnessAction.PASS,
            )

    adapter.inspect_damage = AsyncMock(side_effect=mock_inspect_damage)

    handoff = Stage3HandoffPayload(
        claim_id=claim_id,
        policy_id="POL-RECROP",
        registration_number="MH04RC3333",
        make="Mahindra",
        model="Thar",
        grounded_parts=[p1],
        telemetry={},
    )

    payload = await orchestrator.inspect_claim(handoff)

    assert inspection_calls == 2
    assert len(payload.verified_parts) == 1
    assert payload.verified_parts[0].depth_grade == DepthGrade.L4_CREASED_DENT
    s3_telemetry = payload.telemetry.get("stage3_telemetry", {})
    assert s3_telemetry.get("dynamic_recrops_count") == 1


def test_prompt_engine_tri_stream_and_harness_instructions():
    """Verify prompt engine generates instructions for tri-stream evidence and dynamic recrop harness."""
    ctx = InspectionContext(
        canonical_part_key="quarter_panel_rear_left",
        part_display_name="Rear Left Quarter Panel",
        primary_damage_class="dent",
        make="Skoda",
        model="Slavia",
        iop_ratio=0.22,
    )
    prompt = VLMPromptEngine.build_inspection_prompt(ctx)
    assert "Image 1 (Set-of-Marks)" in prompt
    assert "Image 2 (Raw Crop)" in prompt
    assert "Image 3 (Full Keyframe Frame)" in prompt
    assert "HARNESS ORCHESTRATION & DYNAMIC RE-EXTRACTION" in prompt
    assert "REQUEST_DYNAMIC_RECROP" in prompt
    assert "requested_crop_bbox" in prompt
    assert "reextraction_reason" in prompt
