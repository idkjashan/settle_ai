"""Unit and integration tests for Stage 3 VLM Damage Inspection components."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4
import pytest
import httpx

from app.domain.dual_mask_segmentation.schemas import (
    GroundedDamagedPart,
    OEMPartCatalogueRecord,
    SVGOverlayPayload,
)
from app.domain.vlm_damage_inspection import (
    CircuitBreaker,
    DepthGrade,
    DeterministicMockVLMAdapter,
    FalsePositiveReason,
    GeminiVisionAdapter,
    InspectionContext,
    InspectionCropPair,
    OllamaVisionAdapter,
    OpenAIVisionAdapter,
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
    Stage3Telemetry,
    Stage4HandoffPayload,
    VehicleOrientation,
    VerifiedDamagedPart,
    VLMInspectionOutput,
    VLMProviderFactory,
    VLMProviderType,
    execute_with_jitter_retry,
    get_vlm_adapter,
    is_port_open,
    resolve_ollama_url,
    resolve_wsl2_gateway,
)


# ============================================================================
# 1. Schemas & Enums Tests
# ============================================================================

def test_depth_grades():
    assert DepthGrade.L1_SURFACE_SCUFF == "L1_SURFACE_SCUFF"
    assert DepthGrade.L2_BASECOAT_SCRATCH == "L2_BASECOAT_SCRATCH"
    assert DepthGrade.L3_SHALLOW_DENT_PDR == "L3_SHALLOW_DENT_PDR"
    assert DepthGrade.L4_CREASED_DENT == "L4_CREASED_DENT"
    assert DepthGrade.L5_STRUCTURAL_TEAR == "L5_STRUCTURAL_TEAR"


def test_vehicle_orientation_enum_values():
    """Verify all vehicle orientation classifications for perspective analysis."""
    assert VehicleOrientation.FRONT == "FRONT"
    assert VehicleOrientation.REAR == "REAR"
    assert VehicleOrientation.LEFT_SIDE == "LEFT_SIDE"
    assert VehicleOrientation.RIGHT_SIDE == "RIGHT_SIDE"
    assert VehicleOrientation.FRONT_LEFT_3_QUARTER == "FRONT_LEFT_3_QUARTER"
    assert VehicleOrientation.FRONT_RIGHT_3_QUARTER == "FRONT_RIGHT_3_QUARTER"
    assert VehicleOrientation.REAR_LEFT_3_QUARTER == "REAR_LEFT_3_QUARTER"
    assert VehicleOrientation.REAR_RIGHT_3_QUARTER == "REAR_RIGHT_3_QUARTER"
    assert VehicleOrientation.OVERHEAD_ROOF == "OVERHEAD_ROOF"
    assert VehicleOrientation.UNKNOWN == "UNKNOWN"


def test_vlm_inspection_output_backward_compatibility_defaults():
    """Verify existing VLMInspectionOutput callers and payloads without new fields work seamlessly."""
    output = VLMInspectionOutput(
        is_real_physical_damage=True,
        depth_grade=DepthGrade.L2_BASECOAT_SCRATCH,
        confidence=0.95,
        visual_reasoning_short="Surface scratch on basecoat.",
    )
    assert output.vehicle_orientation == VehicleOrientation.UNKNOWN
    assert output.detected_component is None
    assert output.component_matches_target is True
    assert output.possible_duplicate is False
    assert output.duplicate_of_part_key is None
    assert output.missing_parts_detected == []
    assert output.needs_reidentification is False
    assert output.reidentification_roi_bbox is None


def test_vlm_inspection_output_extended_fields():
    """Verify full instantiation and validation of orientation and component-wise fields."""
    output = VLMInspectionOutput(
        is_real_physical_damage=True,
        depth_grade=DepthGrade.L4_CREASED_DENT,
        confidence=0.92,
        visual_reasoning_short="Deep crease on left fender near headlamp seam.",
        vehicle_orientation=VehicleOrientation.FRONT_LEFT_3_QUARTER,
        detected_component="front_left_fender",
        component_matches_target=False,
        possible_duplicate=True,
        duplicate_of_part_key="front_bumper",
        missing_parts_detected=["fog_lamp_bezel_left"],
        needs_reidentification=True,
        reidentification_roi_bbox=[0.15, 0.20, 0.75, 0.85],
    )
    assert output.vehicle_orientation == VehicleOrientation.FRONT_LEFT_3_QUARTER
    assert output.detected_component == "front_left_fender"
    assert output.component_matches_target is False
    assert output.possible_duplicate is True
    assert output.duplicate_of_part_key == "front_bumper"
    assert output.missing_parts_detected == ["fog_lamp_bezel_left"]
    assert output.needs_reidentification is True
    assert output.reidentification_roi_bbox == [0.15, 0.20, 0.75, 0.85]


def test_false_positive_reasons():
    assert FalsePositiveReason.NONE == "NONE"
    assert FalsePositiveReason.MUD_OR_DIRT == "MUD_OR_DIRT"
    assert FalsePositiveReason.BIRD_DROPPINGS == "BIRD_DROPPINGS"
    assert FalsePositiveReason.CHALK_OR_MARKER == "CHALK_OR_MARKER"
    assert FalsePositiveReason.DECAL_OR_STICKER == "DECAL_OR_STICKER"
    assert FalsePositiveReason.WATER_DROPLET == "WATER_DROPLET"
    assert FalsePositiveReason.SPECULAR_GLARE == "SPECULAR_GLARE"
    assert FalsePositiveReason.ASPHALT_REFLECTION == "ASPHALT_REFLECTION"
    assert FalsePositiveReason.OTHER_NON_DAMAGE == "OTHER_NON_DAMAGE"


def test_stage3_failure_codes():
    assert Stage3FailureCode.S3_FALSE_POSITIVE_FILTERED == "S3_FALSE_POSITIVE_FILTERED"
    assert Stage3FailureCode.ESC_04_PREEXISTING_CORROSION == "ESC-04_PREEXISTING_CORROSION"
    assert Stage3FailureCode.ESC_06_STRUCTURAL_HAZARD == "ESC-06_STRUCTURAL_HAZARD"
    assert Stage3FailureCode.ESC_07_NO_REAL_DAMAGE_DETECTED == "ESC-07_NO_REAL_DAMAGE_DETECTED"


def test_inspection_context_aliases():
    ctx1 = InspectionContext(
        canonical_part_key="front_bumper",
        primary_damage_class="scratch",
        make="Hyundai",
        model="Creta",
        iop_ratio=0.125,
        part_display_name="Front Bumper Fascia",
    )
    assert ctx1.iop_ratio == 0.125
    assert ctx1.final_iop_ratio == 0.125
    assert ctx1.part_display_name == "Front Bumper Fascia"

    # Test alias resolution from dict
    ctx2 = InspectionContext.model_validate({
        "canonical_part_key": "door_front_left",
        "primary_damage_class": "dent",
        "make": "Maruti",
        "model": "Swift",
        "final_iop_ratio": 0.08,
        "display_part_name": "Front Left Door",
    })
    assert ctx2.iop_ratio == 0.08
    assert ctx2.final_iop_ratio == 0.08
    assert ctx2.part_display_name == "Front Left Door"


def test_vlm_inspection_output_validation():
    valid_payload = {
        "is_real_physical_damage": True,
        "false_positive_reason": "NONE",
        "depth_grade": "L3_SHALLOW_DENT_PDR",
        "has_rust_or_oxidation": False,
        "rust_details": None,
        "has_panel_gap_misalignment": False,
        "misalignment_details": None,
        "confidence": 0.94,
        "visual_reasoning_short": "Gradual smooth depression with clearcoat intact.",
    }
    out = VLMInspectionOutput.model_validate(valid_payload)
    assert out.is_real_physical_damage is True
    assert out.depth_grade == DepthGrade.L3_SHALLOW_DENT_PDR
    assert out.confidence == 0.94

    # Invalid confidence range should raise ValidationError
    invalid_conf = {**valid_payload, "confidence": 1.5}
    with pytest.raises(Exception):
        VLMInspectionOutput.model_validate(invalid_conf)


def test_verified_damaged_part_from_grounded_part():
    cat = OEMPartCatalogueRecord(
        canonical_part_key="front_bumper",
        display_part_name="Front Bumper",
        oem_part_number="OEM-12345",
        part_material="polypropylene",
        depreciation_rate_non_zero_dep=0.15,
        oem_part_cost_inr=8500.0,
        rr_labour_inr=1200.0,
        denting_base_labour_inr=0.0,
        full_panel_paint_inr=3500.0,
        pdr_or_polish_flat_inr=800.0,
        is_repairable=True,
        is_safety_critical=False,
    )
    grounded = GroundedDamagedPart(
        canonical_part_key="front_bumper",
        raw_detected_part_classes=["bumper"],
        side_resolution_method="direct",
        display_part_name="Front Bumper",
        oem_part_number="OEM-12345",
        part_material="polypropylene",
        is_repairable=True,
        is_safety_critical=False,
        detected_damage_classes=["scratch"],
        primary_damage_class="scratch",
        final_iop_ratio=0.05,
        iop_percentage=5.0,
        iop_estimation_method="pixel_ratio",
        zoom_clipped_frames_filtered=0,
        persistence_frame_count=3,
        part_confidence=0.91,
        damage_confidence=0.88,
        area_measurement_keyframe="frame_001.jpg",
        vlm_closeup_keyframe="frame_002.jpg",
        som_annotated_crop_path=Path("/tmp/som.jpg"),
        som_raw_crop_path=Path("/tmp/raw.jpg"),
        svg_overlay=SVGOverlayPayload("f1", "0 0 100 100", [], []),
        catalogue_record=cat,
    )
    vlm_out = VLMInspectionOutput(
        is_real_physical_damage=True,
        depth_grade=DepthGrade.L2_BASECOAT_SCRATCH,
        confidence=0.95,
        visual_reasoning_short="Penetrating scratch through clearcoat.",
    )

    verified = VerifiedDamagedPart.from_grounded_part(grounded, vlm_out, latency_ms=120.5)
    assert verified.canonical_part_key == "front_bumper"
    assert verified.depth_grade == DepthGrade.L2_BASECOAT_SCRATCH
    assert verified.vlm_confidence == 0.95
    assert verified.latency_ms == 120.5
    assert verified.catalogue_record == cat


def test_stage4_handoff_payload_dismissed_alias():
    claim_id = uuid4()
    q = QuarantinedPartRecord(
        canonical_part_key="rear_door",
        primary_damage_class="dirt",
        false_positive_reason=FalsePositiveReason.MUD_OR_DIRT,
        visual_reasoning_short="Superficial mud splatter",
        vlm_confidence=0.97,
    )
    payload = Stage4HandoffPayload(
        claim_id=claim_id,
        policy_id="POL-999",
        registration_number="MH02AB1234",
        make="Honda",
        model="City",
        verified_parts=[],
        quarantined_parts=[q],
    )
    assert len(payload.quarantined_parts) == 1
    assert payload.dismissed_parts == payload.quarantined_parts


# ============================================================================
# 2. Config & Exceptions Tests
# ============================================================================

def test_stage3_settings():
    s = Stage3Settings(vlm_provider="mock", request_timeout_seconds=5.0)
    assert s.vlm_provider == "mock"
    assert s.request_timeout_seconds == 5.0
    assert s.circuit_breaker_failure_threshold == 5


def test_exceptions_escalation_codes():
    cid = uuid4()
    p = Path("/tmp/rust.jpg")
    e_rust = Stage3RustOrOxidationError("Rust found", part_key="hood", claim_id=cid, evidence_path=p)
    assert e_rust.escalation_code == "ESC-04"
    assert e_rust.part_key == "hood"
    assert e_rust.claim_id == cid

    e_frame = Stage3StructuralMisalignmentError("Wedged door", part_key="door", claim_id=cid)
    assert e_frame.escalation_code == "ESC-06"

    e_zero = Stage3NoRealDamageDetectedError("No damage", claim_id=cid)
    assert e_zero.escalation_code == "ESC-07"

    e_open = Stage3CircuitBreakerOpenError()
    assert "Circuit Breaker is OPEN" in str(e_open)


# ============================================================================
# 3. Network Utils Tests
# ============================================================================

def test_resolve_wsl2_gateway():
    gw = resolve_wsl2_gateway()
    # In Linux WSL2 this returns an IP or None if not WSL2/routed
    if gw is not None:
        assert isinstance(gw, str)
        assert len(gw.split(".")) == 4


def test_resolve_ollama_url():
    # Calling with localhost should either stay localhost or resolve to gateway
    resolved = resolve_ollama_url("http://localhost:11434")
    assert resolved.startswith("http://")
    assert ":11434" in resolved


# ============================================================================
# 4. Circuit Breaker Tests
# ============================================================================

@pytest.mark.asyncio
async def test_circuit_breaker_state_transitions():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
    assert cb.state == "CLOSED"

    async def failing_call():
        raise RuntimeError("Transient connection failure")

    async def successful_call():
        return "success"

    # First failure: count = 1, still CLOSED
    with pytest.raises(RuntimeError):
        await cb.call(failing_call)
    assert cb.state == "CLOSED"
    assert cb.failure_count == 1

    # Second failure: trips to OPEN
    with pytest.raises(RuntimeError):
        await cb.call(failing_call)
    assert cb.state == "OPEN"

    # Immediately calling should fail fast with Stage3CircuitBreakerOpenError
    with pytest.raises(Stage3CircuitBreakerOpenError):
        await cb.call(successful_call)

    # Wait for recovery timeout
    await asyncio.sleep(0.12)

    # In HALF_OPEN probe, successful call resets state to CLOSED
    res = await cb.call(successful_call)
    assert res == "success"
    assert cb.state == "CLOSED"
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_execute_with_jitter_retry():
    attempts = 0

    async def flaky_call():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ValueError("Temporary glitch")
        return "recovered"

    result = await execute_with_jitter_retry(flaky_call, max_retries=3, base_delays=(0.01, 0.02))
    assert result == "recovered"
    assert attempts == 3


# ============================================================================
# 5. Resilient JSON Parser Tests
# ============================================================================

def test_resilient_parser_clean_string():
    # Markdown fence with trailing comma
    raw1 = "```json\n{\n  \"is_real_physical_damage\": true,\n}\n```"
    cleaned1 = ResilientJSONParser.clean_json_string(raw1)
    assert cleaned1 == '{\n  "is_real_physical_damage": true\n}'

    # Conversational wrapper
    raw2 = "Sure, here is the result: {\"a\": 1, \"b\": 2,} Have a great day!"
    cleaned2 = ResilientJSONParser.clean_json_string(raw2)
    assert cleaned2 == '{"a": 1, "b": 2}'


def test_resilient_parser_parse_and_validate():
    valid_json = """
    ```json
    {
      "is_real_physical_damage": true,
      "false_positive_reason": "NONE",
      "depth_grade": "L2_BASECOAT_SCRATCH",
      "has_rust_or_oxidation": false,
      "has_panel_gap_misalignment": false,
      "confidence": 0.95,
      "visual_reasoning_short": "Clearcoat penetrated with grey primer showing.",
    }
    ```
    """
    out = ResilientJSONParser.parse_and_validate(valid_json, VLMInspectionOutput)
    assert out.is_real_physical_damage is True
    assert out.depth_grade == DepthGrade.L2_BASECOAT_SCRATCH

    # Python bool syntax fallback (True/False)
    python_syntax = """
    {
      "is_real_physical_damage": True,
      "false_positive_reason": "NONE",
      "depth_grade": "L1_SURFACE_SCUFF",
      "has_rust_or_oxidation": False,
      "rust_details": None,
      "has_panel_gap_misalignment": False,
      "confidence": 0.90,
      "visual_reasoning_short": "Surface rub.",
    }
    """
    out2 = ResilientJSONParser.parse_and_validate(python_syntax, VLMInspectionOutput)
    assert out2.depth_grade == DepthGrade.L1_SURFACE_SCUFF

    # Malformed output should raise Stage3MalformedOutputError
    with pytest.raises(Stage3MalformedOutputError):
        ResilientJSONParser.parse_and_validate("Totally invalid text with no json", VLMInspectionOutput)


# ============================================================================
# 6. Deterministic Mock Adapter Tests
# ============================================================================

@pytest.mark.asyncio
async def test_deterministic_mock_vlm_adapter():
    adapter = DeterministicMockVLMAdapter()
    assert await adapter.health_check() is True

    # 1. Rust scenario
    ctx_rust = InspectionContext(
        canonical_part_key="door_rear_right_rust",
        primary_damage_class="scratch",
        make="Tata",
        model="Nexon",
        iop_ratio=0.08,
    )
    res_rust = await adapter.inspect_damage(b"som", b"raw", ctx_rust)
    assert res_rust.has_rust_or_oxidation is True
    assert res_rust.rust_details is not None

    # 2. Structural misalignment scenario
    ctx_gap = InspectionContext(
        canonical_part_key="fender_left_gap_misaligned",
        primary_damage_class="dent",
        make="Tata",
        model="Nexon",
        iop_ratio=0.15,
    )
    res_gap = await adapter.inspect_damage(b"som", b"raw", ctx_gap)
    assert res_gap.has_panel_gap_misalignment is True
    assert res_gap.misalignment_details is not None

    # 3. Contaminant / False Positive scenario (bird droppings)
    ctx_bird = InspectionContext(
        canonical_part_key="windshield_bird_droppings",
        primary_damage_class="dirt",
        make="Tata",
        model="Nexon",
        iop_ratio=0.02,
    )
    res_bird = await adapter.inspect_damage(b"som", b"raw", ctx_bird)
    assert res_bird.is_real_physical_damage is False
    assert res_bird.false_positive_reason == FalsePositiveReason.BIRD_DROPPINGS

    # 4. Crack -> L5_STRUCTURAL_TEAR
    ctx_crack = InspectionContext(
        canonical_part_key="front_bumper",
        primary_damage_class="crack",
        make="Tata",
        model="Nexon",
        iop_ratio=0.04,
    )
    res_crack = await adapter.inspect_damage(b"som", b"raw", ctx_crack)
    assert res_crack.is_real_physical_damage is True
    assert res_crack.depth_grade == DepthGrade.L5_STRUCTURAL_TEAR

    # 5. Small dent <= 0.10 -> L3_SHALLOW_DENT_PDR
    ctx_dent_pdr = InspectionContext(
        canonical_part_key="front_door",
        primary_damage_class="dent",
        make="Tata",
        model="Nexon",
        iop_ratio=0.08,
    )
    res_pdr = await adapter.inspect_damage(b"som", b"raw", ctx_dent_pdr)
    assert res_pdr.depth_grade == DepthGrade.L3_SHALLOW_DENT_PDR

    # 6. Large dent > 0.10 -> L4_CREASED_DENT
    ctx_dent_crease = InspectionContext(
        canonical_part_key="front_door",
        primary_damage_class="dent",
        make="Tata",
        model="Nexon",
        iop_ratio=0.18,
    )
    res_crease = await adapter.inspect_damage(b"som", b"raw", ctx_dent_crease)
    assert res_crease.depth_grade == DepthGrade.L4_CREASED_DENT


# ============================================================================
# 7. Mocked Transport Tests for Cloud & Ollama Adapters
# ============================================================================

@pytest.mark.asyncio
async def test_ollama_adapter_mocked_http():
    expected_inspection = {
        "is_real_physical_damage": True,
        "false_positive_reason": "NONE",
        "depth_grade": "L2_BASECOAT_SCRATCH",
        "has_rust_or_oxidation": False,
        "rust_details": None,
        "has_panel_gap_misalignment": False,
        "misalignment_details": None,
        "confidence": 0.93,
        "visual_reasoning_short": "Basecoat scratch confirmed.",
    }

    def mock_handler(request: httpx.Request) -> httpx.Response:
        if "/api/chat" in str(request.url):
            return httpx.Response(200, json={"message": {"content": json.dumps(expected_inspection)}})
        elif "/api/tags" in str(request.url):
            return httpx.Response(200, json={"models": [{"name": "minicpm-v:8b"}]})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    adapter = OllamaVisionAdapter(base_url="http://test-ollama:11434", timeout=5.0)
    adapter._client = httpx.AsyncClient(transport=transport)

    assert await adapter.health_check() is True

    ctx = InspectionContext(
        canonical_part_key="fender_right",
        primary_damage_class="scratch",
        make="Toyota",
        model="Innova",
        iop_ratio=0.05,
    )
    res = await adapter.inspect_damage(b"som_bytes", b"raw_bytes", ctx)
    assert res.depth_grade == DepthGrade.L2_BASECOAT_SCRATCH
    assert res.confidence == 0.93
    await adapter.aclose()


@pytest.mark.asyncio
async def test_gemini_adapter_mocked_http():
    expected_inspection = {
        "is_real_physical_damage": True,
        "false_positive_reason": "NONE",
        "depth_grade": "L4_CREASED_DENT",
        "has_rust_or_oxidation": False,
        "rust_details": None,
        "has_panel_gap_misalignment": False,
        "misalignment_details": None,
        "confidence": 0.97,
        "visual_reasoning_short": "Creased dent across style line.",
    }

    def mock_handler(request: httpx.Request) -> httpx.Response:
        if "generateContent" in str(request.url):
            return httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": json.dumps(expected_inspection)}]}}]},
            )
        elif "/models/" in str(request.url):
            return httpx.Response(200, json={"name": "models/gemini-2.5-flash"})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    adapter = GeminiVisionAdapter(api_key="mock_key", timeout=5.0)
    adapter._client = httpx.AsyncClient(transport=transport)

    assert await adapter.health_check() is True

    ctx = InspectionContext(
        canonical_part_key="door_rear_left",
        primary_damage_class="dent",
        make="Kia",
        model="Seltos",
        iop_ratio=0.15,
    )
    res = await adapter.inspect_damage(b"som_bytes", b"raw_bytes", ctx)
    assert res.depth_grade == DepthGrade.L4_CREASED_DENT
    assert res.confidence == 0.97
    await adapter.aclose()


@pytest.mark.asyncio
async def test_openai_adapter_mocked_http():
    expected_inspection = {
        "is_real_physical_damage": False,
        "false_positive_reason": "MUD_OR_DIRT",
        "depth_grade": "L1_SURFACE_SCUFF",
        "has_rust_or_oxidation": False,
        "rust_details": None,
        "has_panel_gap_misalignment": False,
        "misalignment_details": None,
        "confidence": 0.95,
        "visual_reasoning_short": "Road dirt particulate on clearcoat.",
    }

    def mock_handler(request: httpx.Request) -> httpx.Response:
        if "/chat/completions" in str(request.url):
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": json.dumps(expected_inspection)}}]},
            )
        elif "/models" in str(request.url):
            return httpx.Response(200, json={"data": [{"id": "gpt-4o-mini"}]})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    adapter = OpenAIVisionAdapter(api_key="mock_key", timeout=5.0)
    adapter._client = httpx.AsyncClient(transport=transport)

    assert await adapter.health_check() is True

    ctx = InspectionContext(
        canonical_part_key="rear_bumper",
        primary_damage_class="dirt",
        make="Mahindra",
        model="Thar",
        iop_ratio=0.03,
    )
    res = await adapter.inspect_damage(b"som_bytes", b"raw_bytes", ctx)
    assert res.is_real_physical_damage is False
    assert res.false_positive_reason == FalsePositiveReason.MUD_OR_DIRT
    await adapter.aclose()


# ============================================================================
# 8. Factory Tests
# ============================================================================

def test_vlm_provider_factory():
    # 1. Explicit mock
    ad_mock = get_vlm_adapter(provider_override="mock")
    assert isinstance(ad_mock, DeterministicMockVLMAdapter)

    # 2. Explicit ollama
    ad_ollama = get_vlm_adapter(provider_override="ollama")
    assert isinstance(ad_ollama, OllamaVisionAdapter)

    # 3. Explicit gemini
    ad_gemini = get_vlm_adapter(provider_override="gemini")
    assert isinstance(ad_gemini, GeminiVisionAdapter)

    # 4. Explicit openai
    ad_openai = get_vlm_adapter(provider_override="openai")
    assert isinstance(ad_openai, OpenAIVisionAdapter)

    # 5. Facade class
    ad_facade = VLMProviderFactory.get_adapter("mock")
    assert isinstance(ad_facade, DeterministicMockVLMAdapter)
