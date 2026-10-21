"""
app/domain/settlement_escalation/apportionment.py
Pro-rata multi-part cash apportionment engine with penny balancing and unrepaired ledger commit.
"""
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import List, Tuple
from app.domain.actuarial_pricing.schemas import ActuarialEstimateDTO, ActuarialLineItemDTO
from app.domain.settlement_escalation.schemas import ApportionedPartPayoutDTO
from app.infrastructure.db.repositories import UnrepairedClaimsRepository

logger = logging.getLogger(__name__)


class MultiPartApportionmentEngine:
    """
    Apportions a lump-sum cash settlement across all damaged parts proportionally to their
    pre-tax gross repair costs, balances residual rounding cents, and records each part
    into the unrepaired claims ledger to prevent repeat claim fraud (ESC-03).
    """

    def apportion_settlement(
        self,
        settled_amount_inr: Decimal,
        line_items: List[ActuarialLineItemDTO],
    ) -> List[ApportionedPartPayoutDTO]:
        """
        Distributes settled_amount_inr across line_items using exact pro-rata math with penny balancing.
        Guarantees sum(apportioned_amount_inr) == settled_amount_inr.
        """
        if not line_items:
            return []

        if len(line_items) == 1:
            item = line_items[0]
            return [
                ApportionedPartPayoutDTO(
                    canonical_part_key=item.canonical_part_key,
                    display_part_name=item.display_part_name,
                    damage_class=item.depth_grade,
                    gross_line_item_inr=item.gross_line_item_total_inr,
                    apportioned_amount_inr=settled_amount_inr.quantize(Decimal("0.01")),
                )
            ]

        total_gross = sum((item.gross_line_item_total_inr for item in line_items), Decimal("0.00"))
        if total_gross <= Decimal("0.00"):
            # Uniform split fallback
            per_item = (settled_amount_inr / Decimal(len(line_items))).quantize(Decimal("0.01"))
            allocated = []
            running_sum = Decimal("0.00")
            for i, item in enumerate(line_items):
                amt = per_item
                if i == len(line_items) - 1:
                    amt = settled_amount_inr - running_sum
                running_sum += amt
                allocated.append(
                    ApportionedPartPayoutDTO(
                        canonical_part_key=item.canonical_part_key,
                        display_part_name=item.display_part_name,
                        damage_class=item.depth_grade,
                        gross_line_item_inr=item.gross_line_item_total_inr,
                        apportioned_amount_inr=amt,
                    )
                )
            return allocated

        # Pro-rata calculation
        preliminary_allocations: List[Tuple[ActuarialLineItemDTO, Decimal]] = []
        running_sum = Decimal("0.00")
        max_idx = 0
        max_gross = Decimal("-1.00")

        for idx, item in enumerate(line_items):
            weight = item.gross_line_item_total_inr / total_gross
            part_share = (settled_amount_inr * weight).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            preliminary_allocations.append((item, part_share))
            running_sum += part_share

            if item.gross_line_item_total_inr > max_gross:
                max_gross = item.gross_line_item_total_inr
                max_idx = idx

        # Penny balancing
        residual_delta = settled_amount_inr - running_sum
        if residual_delta != Decimal("0.00"):
            target_item, target_amt = preliminary_allocations[max_idx]
            preliminary_allocations[max_idx] = (target_item, target_amt + residual_delta)
            logger.debug(
                f"Apportionment penny balance adjustment of ₹{residual_delta} credited to '{target_item.canonical_part_key}'"
            )

        result: List[ApportionedPartPayoutDTO] = []
        for item, final_amt in preliminary_allocations:
            result.append(
                ApportionedPartPayoutDTO(
                    canonical_part_key=item.canonical_part_key,
                    display_part_name=item.display_part_name,
                    damage_class=item.depth_grade,
                    gross_line_item_inr=item.gross_line_item_total_inr,
                    apportioned_amount_inr=final_amt,
                )
            )

        return result

    async def commit_to_ledger(
        self,
        unrepaired_repo: UnrepairedClaimsRepository,
        registration_number: str,
        apportioned_parts: List[ApportionedPartPayoutDTO],
    ) -> None:
        """
        Commits each apportioned part into the unrepaired_claims_ledger table.
        """
        for part in apportioned_parts:
            try:
                await unrepaired_repo.record_cash_payout(
                    registration_number=registration_number,
                    canonical_part_key=part.canonical_part_key,
                    damage_class=part.damage_class,
                    settled_amount=part.apportioned_amount_inr,
                )
                logger.info(
                    f"Committed part '{part.canonical_part_key}' for vehicle {registration_number} "
                    f"to unrepaired claims ledger with cash payout ₹{part.apportioned_amount_inr}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to record part '{part.canonical_part_key}' in unrepaired claims ledger: {e}"
                )
                raise


apportionment_engine = MultiPartApportionmentEngine()

