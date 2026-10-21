"""
tests/settlement_escalation/test_dossier_builder.py
Unit tests for Human Adjuster Review Dossier compilation, escalation codes, and surveyor checklists.
"""
import uuid
import pytest
from app.domain.settlement_escalation.dossier_builder import (
    ESCALATION_DESCRIPTIONS,
    HumanAdjusterDossierBuilder,
)


@pytest.fixture
def builder() -> HumanAdjusterDossierBuilder:
    return HumanAdjusterDossierBuilder()


@pytest.mark.parametrize("esc_code", list(ESCALATION_DESCRIPTIONS.keys()))
def test_escalation_codes_mapping(builder, esc_code):
    """Verifies that all standard escalation codes (ESC-00 through ESC-09 + ESC-USER-REJECT) compile correctly."""
    claim_id = uuid.uuid4()
    dossier = builder.build_dossier(
        claim_id=claim_id,
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        escalation_code=esc_code,
    )

    expected_desc, expected_action = ESCALATION_DESCRIPTIONS[esc_code]
    assert dossier.escalation_code == esc_code
    assert dossier.escalation_reason == expected_desc
    assert dossier.recommended_surveyor_action == expected_action
    assert dossier.dossier_id.startswith(f"DOSSIER-{esc_code}-")


def test_custom_escalation_reason_appended(builder):
    """Verifies that a custom escalation reason is appended to the standard description."""
    dossier = builder.build_dossier(
        claim_id=uuid.uuid4(),
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        escalation_code="ESC-07",
        custom_reason="Zero damage detected across front bumper.",
    )
    assert "Zero damage detected across front bumper" in dossier.escalation_reason


def test_standardized_6_point_surveyor_checklist(builder):
    """Verifies that the compiled dossier contains the 6-point physical inspection checklist."""
    dossier = builder.build_dossier(
        claim_id=uuid.uuid4(),
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        escalation_code="ESC-02",
    )

    checklist = dossier.surveyor_checklist
    assert len(checklist) == 6
    assert any("VIN stamp" in item for item in checklist)
    assert any("HSRP rivets" in item for item in checklist)
    assert any("coating thickness" in item for item in checklist)
    assert any("Set-of-Marks" in item for item in checklist)
    assert any("oxidation" in item for item in checklist)


def test_forensic_telemetry_and_actuarial_summary_packaging(builder):
    """Verifies that diagnostic forensic telemetry and actuarial summary dictionaries are stored."""
    telemetry = {"fast_fail": {"passed": True}, "cut_detected": False}
    summary = {"gross_repair": "15000.00", "net_liability": "13000.00"}

    dossier = builder.build_dossier(
        claim_id=uuid.uuid4(),
        policy_id="POL-HAPPY-001",
        registration_number="MH12DE1433",
        escalation_code="ESC-08",
        forensic_telemetry=telemetry,
        actuarial_summary=summary,
    )

    assert dossier.forensic_telemetry == telemetry
    assert dossier.actuarial_summary == summary