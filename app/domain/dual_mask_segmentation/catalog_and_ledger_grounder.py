from typing import List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.exceptions import (
    Stage2LowConfidenceOrNoDamageError,
    Stage2OppositeSideMultiHitError,
    Stage2SafetyCriticalError,
    Stage2UnrepairedRepeatError,
)
from app.domain.dual_mask_segmentation.schemas import (
    GroundingCheckResult,
    GroupedPartCandidate,
    OEMPartCatalogueRecord,
    Stage2FailureCode,
)
from app.domain.dual_mask_segmentation.taxonomy import (
    LEFT_SIDE_PARTS,
    RIGHT_SIDE_PARTS,
    SAFETY_CRITICAL_DAMAGE_CLASSES,
    SAFETY_CRITICAL_PARTS,
)
from app.infrastructure.db.models import (
    InsuredPolicy,
    OEMPartsCatalogue,
    UnrepairedClaimsLedger,
)


class CatalogAndLedgerGrounder:
    """Joins detected part candidates against PostgreSQL oem_parts_catalogue and
    unrepaired_claims_ledger, and evaluates ESC-03, ESC-05, ESC-06, and ESC-07.
    """

    def __init__(self, db_session: AsyncSession, settings: Optional[Stage2Settings] = None):
        self.db = db_session
        self.settings = settings or Stage2Settings()

    async def ground_and_check_guardrails(
        self, policy_id: str, candidates: List[GroupedPartCandidate]
    ) -> GroundingCheckResult:
        # 1. ESC-07 Check: Zero Damage Candidates or Low Confidence
        if not candidates:
            raise Stage2LowConfidenceOrNoDamageError(
                message="No exterior panel damage survived multi-frame persistence and spillover filtering.",
                failure_codes=[Stage2FailureCode.S2_NO_DAMAGE_DETECTED.value],
            )

        for cand in candidates:
            if (
                cand.part_confidence < self.settings.high_conf_escalation_floor
                or cand.damage_confidence < self.settings.high_conf_escalation_floor
            ):
                raise Stage2LowConfidenceOrNoDamageError(
                    message=f"Low segmentation confidence on {cand.canonical_part_key}.",
                    failure_codes=[Stage2FailureCode.S2_LOW_SEGMENTATION_CONFIDENCE.value],
                )

        # 2. Fetch Policy Context (registration_number, make, model)
        pol_stmt = select(InsuredPolicy).where(InsuredPolicy.policy_id == policy_id)
        pol_res = await self.db.execute(pol_stmt)
        policy = pol_res.scalar_one_or_none()
        if not policy:
            raise Stage2LowConfidenceOrNoDamageError(
                message=f"Policy {policy_id} not found during Stage 2 grounding.",
                failure_codes=[Stage2FailureCode.S2_OEM_CATALOGUE_PART_MISSING.value],
            )

        # 3. ESC-05 Check: Opposite-Side Multi-Hit Detection
        part_keys = {c.canonical_part_key for c in candidates}
        left_hits = sorted(part_keys.intersection(LEFT_SIDE_PARTS))
        right_hits = sorted(part_keys.intersection(RIGHT_SIDE_PARTS))
        if left_hits and right_hits:
            raise Stage2OppositeSideMultiHitError(
                message=f"Opposite-side multi-hit detected: left={left_hits}, right={right_hits}.",
                failure_codes=[Stage2FailureCode.S2_OPPOSITE_SIDE_MULTI_HIT.value],
            )

        # 4. ESC-03 Check: Query Unrepaired Claims Ledger
        ledger_stmt = select(UnrepairedClaimsLedger).where(
            UnrepairedClaimsLedger.registration_number == policy.registration_number,
            UnrepairedClaimsLedger.canonical_part_key.in_(list(part_keys)),
            UnrepairedClaimsLedger.is_repaired_verified.is_(False),
        )
        ledger_res = await self.db.execute(ledger_stmt)
        existing_unrepaired = ledger_res.scalars().first()
        if existing_unrepaired is not None:
            raise Stage2UnrepairedRepeatError(
                message=(
                    f"Prior unrepaired cash-in-lieu settlement exists for "
                    f"{existing_unrepaired.canonical_part_key} on {policy.registration_number}."
                ),
                failure_codes=[Stage2FailureCode.S2_UNREPAIRED_REPEAT_CLAIM.value],
            )

        # 5. Lookup OEM Parts Catalogue & Evaluate ESC-06 Safety Rules
        cat_stmt = select(OEMPartsCatalogue).where(
            OEMPartsCatalogue.make == policy.make,
            OEMPartsCatalogue.model == policy.model,
            OEMPartsCatalogue.canonical_part_key.in_(list(part_keys)),
        )
        cat_res = await self.db.execute(cat_stmt)
        cat_rows = {row.canonical_part_key: row for row in cat_res.scalars().all()}

        verified_pairs: List[Tuple[GroupedPartCandidate, OEMPartCatalogueRecord]] = []
        for cand in candidates:
            row = cat_rows.get(cand.canonical_part_key)
            if row is None:
                raise Stage2LowConfidenceOrNoDamageError(
                    message=f"OEM part schedule missing for {policy.make} {policy.model} {cand.canonical_part_key}.",
                    failure_codes=[Stage2FailureCode.S2_OEM_CATALOGUE_PART_MISSING.value],
                )

            cat_rec = OEMPartCatalogueRecord(
                canonical_part_key=row.canonical_part_key,
                display_part_name=row.display_part_name,
                oem_part_number=row.oem_part_number,
                part_material=row.part_material,
                depreciation_rate_non_zero_dep=float(getattr(row, "depreciation_rate_non_zero_dep", 0.0)),
                oem_part_cost_inr=float(row.oem_part_cost_inr),
                rr_labour_inr=float(row.rr_labour_inr),
                denting_base_labour_inr=float(row.denting_base_labour_inr),
                full_panel_paint_inr=float(row.full_panel_paint_inr),
                pdr_or_polish_flat_inr=float(row.pdr_or_polish_flat_inr),
                is_repairable=bool(row.is_repairable),
                is_safety_critical=bool(row.is_safety_critical),
            )

            # ESC-06 Safety-Critical Check
            has_safety_dmg_class = bool(
                set(cand.detected_damage_classes).intersection(SAFETY_CRITICAL_DAMAGE_CLASSES)
            )
            if (
                cat_rec.is_safety_critical
                or cand.canonical_part_key in SAFETY_CRITICAL_PARTS
                or has_safety_dmg_class
            ):
                raise Stage2SafetyCriticalError(
                    message=(
                        f"Safety-critical damage detected on {cat_rec.display_part_name} "
                        f"({cand.primary_damage_class}). Routing to physical garage inspection."
                    ),
                    failure_codes=[Stage2FailureCode.S2_SAFETY_CRITICAL_PART_DAMAGED.value],
                )

            verified_pairs.append((cand, cat_rec))

        return GroundingCheckResult(
            registration_number=policy.registration_number,
            make=policy.make,
            model=policy.model,
            verified_pairs=verified_pairs,
        )
