"""
app/domain/settlement_escalation/dossier_builder.py
Compiles comprehensive claims investigation dossiers for escalated claims.
"""
from datetime import datetime, timezone
import random
from typing import Any, Dict, List, Optional
from uuid import UUID
from app.domain.settlement_escalation.schemas import HumanAdjusterDossierDTO

ESCALATION_DESCRIPTIONS = {
    "ESC-00": ("Fast-Fail Container / Quality Rejection", "Inspect physical media, request live walkaround video re-upload."),
    "ESC-01": ("Vehicle Identity Mismatch (Plate OCR / Paint HSV)", "Dispatch forensic surveyor to verify chassis VIN, RC book, and body paint respray."),
    "ESC-02": ("Video Continuity Splicing / Scene Cut Detected", "Require mandatory in-person garage physical surveyor assessment due to video tampering flags."),
    "ESC-03": ("Prior Unrepaired Repeat Damage Claim (Double-Dipping)", "Verify repair receipts for previous claim; inspect panel for unbroken previous accident damage."),
    "ESC-04": ("Pre-Existing Rust / Flaking Putty Detected by VLM", "Inspect damage site for brown oxidation or non-fresh impact surface aging."),
    "ESC-05": ("Opposite-Side Multi-Hit Impact Inconsistency", "Examine multi-panel damage vectors; verify if multiple distinct incidents were combined."),
    "ESC-06": ("Safety-Critical Component Damaged (Windshield / Wheel / Structural)", "Perform mandatory garage inspection for wheel alignment, structural apron, or glass integrity."),
    "ESC-07": ("Low AI Forensic Detection Confidence (<55%)", "Conduct standard desk adjuster photo verification and line-item review."),
    "ESC-08": ("Estimated Repair Exceeds Autonomous Ceiling (> ₹25,000)", "Assign licensed IRDAI Category-A surveyor to execute formal physical garage estimate."),
    "ESC-09": ("OEM Catalogue Part / Segment Fallback Missing", "Contact OEM parts supplier or regional dealership for non-standard catalogue part pricing."),
    "ESC-USER-REJECT": ("Claimant Selected Authorized Network Cashless Garage", "Issue workshop authorization work order and schedule vehicle inspection at partner network garage."),
}

STANDARD_SURVEYOR_CHECKLIST = [
    "Verify chassis VIN stamp against insurance policy schedule and RC certificate.",
    "Verify front and rear license plates for non-tampered HSRP rivets.",
    "Measure panel paint coating thickness using digital ultrasonic paint gauge.",
    "Inspect underlying frame, cross-members, and aprons for unaligned structural deformation.",
    "Cross-examine damaged panel against Auto-Settle AI Set-of-Marks keyframe forensic crops.",
    "Audit for pre-existing oxidation, rust pitting, or previous non-authorized body filler.",
]


class HumanAdjusterDossierBuilder:
    """
    Constructs HumanAdjusterDossierDTO with complete diagnostic audit trail and surveyor checklist.
    """

    def build_dossier(
        self,
        claim_id: UUID,
        policy_id: str,
        registration_number: str,
        escalation_code: str,
        forensic_telemetry: Optional[Dict[str, Any]] = None,
        actuarial_summary: Optional[Dict[str, Any]] = None,
        custom_reason: Optional[str] = None,
    ) -> HumanAdjusterDossierDTO:
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y%m%d")
        rand_suffix = f"{random.randint(1000, 9999)}"
        dossier_id = f"DOSSIER-{escalation_code}-{date_str}-{rand_suffix}"

        desc, action = ESCALATION_DESCRIPTIONS.get(
            escalation_code,
            ("Claim Escalation for Surveyor Review", "Assign field adjuster for physical inspection.")
        )
        if custom_reason:
            desc = f"{desc}: {custom_reason}"

        return HumanAdjusterDossierDTO(
            dossier_id=dossier_id,
            claim_id=claim_id,
            policy_id=policy_id,
            registration_number=registration_number,
            escalation_code=escalation_code,
            escalation_reason=desc,
            recommended_surveyor_action=action,
            forensic_telemetry=forensic_telemetry or {},
            actuarial_summary=actuarial_summary,
            surveyor_checklist=list(STANDARD_SURVEYOR_CHECKLIST),
            compiled_at=now,
        )


dossier_builder = HumanAdjusterDossierBuilder()

