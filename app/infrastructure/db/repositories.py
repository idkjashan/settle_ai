import uuid
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.models import InsuredPolicy, Claim, OemPart, UnrepairedClaim

class PolicyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, policy_id: str) -> Optional[InsuredPolicy]:
        stmt = select(InsuredPolicy).where(InsuredPolicy.policy_id == policy_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_registration(self, registration_number: str) -> Optional[InsuredPolicy]:
        stmt = select(InsuredPolicy).where(InsuredPolicy.registration_number == registration_number)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ClaimRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, claim_id: uuid.UUID) -> Optional[Claim]:
        stmt = select(Claim).where(Claim.claim_id == claim_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def check_historical_duplicate(self, video_sha256: str) -> bool:
        stmt = (
            select(Claim.claim_id)
            .where(
                Claim.video_sha256 == video_sha256,
                Claim.claim_status.notin_(["REJECTED_FAST_FAIL", "REJECTED_STAGE0"]),
                Claim.is_demo_rehearsal == False,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create_claim(self, claim: Claim) -> Claim:
        self.session.add(claim)
        await self.session.commit()
        await self.session.refresh(claim)
        return claim

    async def update_claim_stage(
        self,
        claim_id: uuid.UUID,
        stage: str,
        status: str,
        escalation_code: Optional[str] = None,
        failure_codes: Optional[List[str]] = None,
        telemetry_update: Optional[Dict[str, Any]] = None,
        telemetry_column: Optional[str] = None,
    ) -> Optional[Claim]:
        claim = await self.get_by_id(claim_id)
        if not claim:
            return None

        claim.current_stage = stage
        claim.claim_status = status
        if escalation_code:
            claim.escalation_code = escalation_code
        if failure_codes:
            claim.failure_codes = failure_codes
        if telemetry_update and telemetry_column:
            setattr(claim, telemetry_column, telemetry_update)

        await self.session.commit()
        await self.session.refresh(claim)
        return claim


class OemRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_part(self, make: str, model: str, canonical_part_key: str) -> Optional[OemPart]:
        stmt = select(OemPart).where(
            OemPart.make.ilike(make),
            OemPart.model.ilike(model),
            OemPart.canonical_part_key == canonical_part_key,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class UnrepairedClaimsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def has_unrepaired_claim(self, registration_number: str, canonical_part_key: str) -> bool:
        stmt = select(UnrepairedClaim.ledger_id).where(
            UnrepairedClaim.registration_number == registration_number,
            UnrepairedClaim.canonical_part_key == canonical_part_key,
            UnrepairedClaim.is_repaired_verified == False,
        ).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def record_cash_payout(
        self,
        registration_number: str,
        canonical_part_key: str,
        damage_class: str,
        settled_amount: Decimal,
    ) -> UnrepairedClaim:
        record = UnrepairedClaim(
            registration_number=registration_number,
            canonical_part_key=canonical_part_key,
            damage_class=damage_class,
            settled_amount_inr=settled_amount,
            is_repaired_verified=False,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record


class DemoResetRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def reset_demo_state(self) -> Dict[str, Any]:
        # Delete test/rehearsal claims or demo policy claims
        del_stmt = delete(Claim).where(
            (Claim.is_demo_rehearsal == True) | (Claim.policy_id.like("POL-HAPPY-%"))
        )
        res = await self.session.execute(del_stmt)
        deleted_claims = res.rowcount

        # Reset cash claims YTD on POL-HAPPY-001
        upd_stmt = (
            update(InsuredPolicy)
            .where(InsuredPolicy.policy_id == "POL-HAPPY-001")
            .values(cash_claims_ytd=0)
        )
        await self.session.execute(upd_stmt)
        await self.session.commit()

        return {"deleted_claims": deleted_claims, "reset_policy": "POL-HAPPY-001"}
