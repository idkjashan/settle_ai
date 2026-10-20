import time
from datetime import date
from typing import List, Optional
from app.infrastructure.db.repositories import PolicyRepository, ClaimRepository
from app.domain.fast_fail_gate.schemas import Tier1GateReport, FastFailFailureCode
from app.core.logging import logger

class PolicyAndDedupeGate:
    def __init__(self, policy_repo: PolicyRepository, claim_repo: ClaimRepository):
        self.policy_repo = policy_repo
        self.claim_repo = claim_repo

    async def validate(self, policy_id: str, sha256_hex: str, is_demo_rehearsal: bool = False) -> Tier1GateReport:
        t0 = time.perf_counter()
        failure_codes: List[FastFailFailureCode] = []
        today = date.today()

        # 1. Fetch policy
        policy = await self.policy_repo.get_by_id(policy_id)
        if not policy:
            failure_codes.append(FastFailFailureCode.POLICY_NOT_FOUND)
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return Tier1GateReport(
                passed=False,
                policy_id=policy_id,
                sha256_hex=sha256_hex,
                failure_codes=failure_codes,
                duration_ms=duration_ms,
            )

        # 2. Check active status
        if policy.policy_status != "ACTIVE":
            failure_codes.append(FastFailFailureCode.POLICY_INACTIVE)

        # 3. Check coverage window
        if not (policy.policy_start_date <= today <= policy.policy_end_date):
            failure_codes.append(FastFailFailureCode.POLICY_EXPIRED_OR_NOT_STARTED)

        # 4. Check annual claim cap
        if policy.cash_claims_ytd >= policy.max_cash_claims_per_year:
            failure_codes.append(FastFailFailureCode.ANNUAL_CASH_CLAIM_LIMIT_REACHED)

        # 5. Check historical video duplicate (skipped during demo rehearsal)
        if not is_demo_rehearsal:
            is_dup = await self.claim_repo.check_historical_duplicate(sha256_hex)
            if is_dup:
                failure_codes.append(FastFailFailureCode.DUPLICATE_VIDEO_SUBMISSION)

        duration_ms = (time.perf_counter() - t0) * 1000.0
        passed = len(failure_codes) == 0

        logger.info(
            f"Tier-1 Gate for policy={policy_id}: passed={passed}, codes={[c.value for c in failure_codes]} ({duration_ms:.2f}ms)"
        )

        return Tier1GateReport(
            passed=passed,
            policy_id=policy_id,
            sha256_hex=sha256_hex,
            failure_codes=failure_codes,
            policy_status=policy.policy_status,
            cash_claims_ytd=policy.cash_claims_ytd,
            max_cash_claims_per_year=policy.max_cash_claims_per_year,
            duration_ms=duration_ms,
        )

