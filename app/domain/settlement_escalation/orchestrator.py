"""
app/domain/settlement_escalation/orchestrator.py
Async Orchestrator managing cash settlement finalization, unrepaired ledger commit,
instant voucher issuance, escalation dossier compilation, and SSE event streaming.
"""
from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.actuarial_pricing.schemas import ActuarialEstimateDTO, ActuarialLineItemDTO
from app.domain.negotiation_chatbot.exceptions import InvalidOfferTokenError
from app.domain.negotiation_chatbot.hmac_signer import HMACOfferSigner, hmac_offer_signer
from app.domain.negotiation_chatbot.schemas import OfferCardDTO
from app.domain.settlement_escalation.apportionment import (
    MultiPartApportionmentEngine,
    apportionment_engine,
)
from app.domain.settlement_escalation.dossier_builder import (
    HumanAdjusterDossierBuilder,
    dossier_builder,
)
from app.domain.settlement_escalation.exceptions import (
    EscalationDossierError,
    SettlementError,
    VoucherGenerationError,
)
from app.domain.settlement_escalation.schemas import (
    HumanAdjusterDossierDTO,
    SettlementVoucherDTO,
)
from app.domain.settlement_escalation.voucher_generator import (
    SettlementVoucherGenerator,
    voucher_generator,
)
from app.infrastructure.cache.redis_manager import RedisManager, redis_manager
from app.infrastructure.db.repositories import (
    ClaimRepository,
    PolicyRepository,
    UnrepairedClaimsRepository,
)

logger = logging.getLogger(__name__)


class Stage6SettlementOrchestrator:
    """
    Coordinates Stage 6 settlement finalization and escalation workflows.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        redis_mgr: Optional[RedisManager] = None,
        signer: Optional[HMACOfferSigner] = None,
        apportioner: Optional[MultiPartApportionmentEngine] = None,
        voucher_gen: Optional[SettlementVoucherGenerator] = None,
        dossier_bld: Optional[HumanAdjusterDossierBuilder] = None,
        claim_repo: Optional[ClaimRepository] = None,
        policy_repo: Optional[PolicyRepository] = None,
        unrepaired_repo: Optional[UnrepairedClaimsRepository] = None,
    ):
        self.db_session = db_session
        self.redis_mgr = redis_mgr or redis_manager
        self.signer = signer or hmac_offer_signer
        self.apportioner = apportioner or apportionment_engine
        self.voucher_gen = voucher_gen or voucher_generator
        self.dossier_bld = dossier_bld or dossier_builder
        self.claim_repo = claim_repo or ClaimRepository(db_session)
        self.policy_repo = policy_repo or PolicyRepository(db_session)
        self.unrepaired_repo = unrepaired_repo or UnrepairedClaimsRepository(db_session)

    async def finalize_settlement(
        self,
        claim_id: UUID,
        accepted_offer: OfferCardDTO,
        beneficiary_upi_id: Optional[str] = None,
    ) -> SettlementVoucherDTO:
        """
        Executes final cash settlement:
        1. Validates HMAC signature on accepted_offer (rejects client DOM tampering).
        2. Retrieves Claim & Policy from PostgreSQL.
        3. Apportions accepted amount across all line items from actuarial_estimate.
        4. Commits each part into unrepaired_claims_ledger (ESC-03 prevention).
        5. Issues digital SettlementVoucherDTO with unique reference & SHA-256 seal.
        6. Persists voucher in PostgreSQL Claim table & updates status to SETTLED_CASH_IN_LIEU.
        7. Publishes CLAIM_SETTLED_CASH_IN_LIEU event to Redis SSE stream.
        """
        # 1. Cryptographic HMAC validation
        is_valid = self.signer.verify_offer(
            claim_id=accepted_offer.claim_id,
            round_num=accepted_offer.round_num,
            amount_inr=accepted_offer.amount_inr,
            expires_at_epoch=accepted_offer.expires_at_epoch,
            signature=accepted_offer.hmac_signature,
        )
        if not is_valid:
            logger.warning(
                f"HMAC offer validation failed for claim {claim_id}: amount ₹{accepted_offer.amount_inr}, "
                f"round {accepted_offer.round_num}, expires {accepted_offer.expires_at_epoch}"
            )
            raise InvalidOfferTokenError(
                "Offer card signature verification failed. The offer may have been tampered with or expired."
            )

        # 2. Retrieve Claim and Policy
        claim = await self.claim_repo.get_by_id(claim_id)
        if not claim:
            raise SettlementError(f"Claim {claim_id} not found in database.")

        if claim.claim_status == "SETTLED_CASH_IN_LIEU" and claim.settlement_voucher:
            logger.info(f"Claim {claim_id} is already settled. Returning existing voucher.")
            return SettlementVoucherDTO.model_validate(claim.settlement_voucher)

        policy = await self.policy_repo.get_by_id(claim.policy_id)
        vehicle_make_model = f"{policy.make} {policy.model}" if policy else "Insured Vehicle"
        registration_number = policy.registration_number if policy else "MH-REG-DEFAULT"

        # 3. Extract line items from actuarial_estimate
        line_items: List[ActuarialLineItemDTO] = []
        if claim.actuarial_estimate and "line_items" in claim.actuarial_estimate:
            for item_dict in claim.actuarial_estimate["line_items"]:
                try:
                    line_items.append(ActuarialLineItemDTO.model_validate(item_dict))
                except Exception as e:
                    logger.warning(f"Failed to parse line item for claim {claim_id}: {e}")

        # 4. Pro-rata apportionment
        apportioned_parts = self.apportioner.apportion_settlement(
            settled_amount_inr=accepted_offer.amount_inr,
            line_items=line_items,
        )

        # 5. Commit to unrepaired claims ledger
        try:
            await self.apportioner.commit_to_ledger(
                unrepaired_repo=self.unrepaired_repo,
                registration_number=registration_number,
                apportioned_parts=apportioned_parts,
            )
        except Exception as e:
            logger.error(f"Failed to commit parts to unrepaired claims ledger for {claim_id}: {e}")
            raise SettlementError(f"Failed to record unrepaired parts ledger: {e}")

        # 6. Generate Voucher
        voucher = self.voucher_gen.generate_voucher(
            claim_id=claim_id,
            policy_id=claim.policy_id,
            registration_number=registration_number,
            vehicle_make_model=vehicle_make_model,
            settled_amount_inr=accepted_offer.amount_inr,
            apportioned_parts=apportioned_parts,
            beneficiary_upi_id=beneficiary_upi_id,
        )

        # 7. Persist in DB
        await self.claim_repo.update_settlement_voucher(
            claim_id=claim_id,
            voucher_data=voucher.to_dict(),
            status="SETTLED_CASH_IN_LIEU",
        )

        # 8. Publish SSE Event
        try:
            await self.redis_mgr.publish_event(
                claim_id=claim_id,
                event_name="CLAIM_SETTLED_CASH_IN_LIEU",
                payload={
                    "claim_id": str(claim_id),
                    "voucher_id": voucher.voucher_id,
                    "settled_amount_inr": str(voucher.settled_amount_inr),
                    "disbursement_ref": voucher.disbursement_ref,
                    "digital_signature_sha256": voucher.digital_signature_sha256,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to publish CLAIM_SETTLED_CASH_IN_LIEU event for {claim_id}: {e}")

        logger.info(
            f"Successfully finalized settlement for claim {claim_id}: voucher {voucher.voucher_id}, "
            f"amount ₹{voucher.settled_amount_inr}"
        )
        return voucher

    async def escalate_claim(
        self,
        claim_id: UUID,
        escalation_code: str,
        escalation_reason: Optional[str] = None,
        telemetry: Optional[Dict[str, Any]] = None,
    ) -> HumanAdjusterDossierDTO:
        """
        Escalates claim to human surveyor review or routes to cashless network garage:
        1. Compiles HumanAdjusterDossierDTO with forensic telemetry & surveyor checklist.
        2. Updates Claim in PostgreSQL with appropriate status and escalation code.
        3. Publishes SSE event to Redis.
        """
        claim = await self.claim_repo.get_by_id(claim_id)
        if not claim:
            raise SettlementError(f"Claim {claim_id} not found in database.")

        policy = await self.policy_repo.get_by_id(claim.policy_id)
        registration_number = policy.registration_number if policy else "MH-REG-DEFAULT"

        combined_telemetry = {}
        if claim.fast_fail_telemetry:
            combined_telemetry["fast_fail"] = claim.fast_fail_telemetry
        if claim.vehicle_continuity_telemetry:
            combined_telemetry["continuity"] = claim.vehicle_continuity_telemetry
        if claim.dual_mask_telemetry:
            combined_telemetry["dual_mask"] = claim.dual_mask_telemetry
        if claim.vlm_inspection_telemetry:
            combined_telemetry["vlm"] = claim.vlm_inspection_telemetry
        if telemetry:
            combined_telemetry.update(telemetry)

        actuarial_summary = None
        if claim.actuarial_estimate and "summary" in claim.actuarial_estimate:
            actuarial_summary = claim.actuarial_estimate["summary"]

        dossier = self.dossier_bld.build_dossier(
            claim_id=claim_id,
            policy_id=claim.policy_id,
            registration_number=registration_number,
            escalation_code=escalation_code,
            forensic_telemetry=combined_telemetry,
            actuarial_summary=actuarial_summary,
            custom_reason=escalation_reason,
        )

        target_status = "ROUTED_CASHLESS_GARAGE" if escalation_code == "ESC-USER-REJECT" else "ESCALATED_HUMAN_REVIEW"

        await self.claim_repo.update_claim_stage(
            claim_id=claim_id,
            stage="STAGE_6_ESCALATION",
            status=target_status,
            escalation_code=escalation_code,
            failure_codes=[escalation_code],
            telemetry_update=dossier.to_dict(),
            telemetry_column="vlm_inspection_telemetry" if not claim.vlm_inspection_telemetry else None,
        )

        # Publish SSE Event
        event_name = "CLAIM_ROUTED_CASHLESS_GARAGE" if escalation_code == "ESC-USER-REJECT" else "CLAIM_ESCALATED"
        try:
            await self.redis_mgr.publish_event(
                claim_id=claim_id,
                event_name=event_name,
                payload={
                    "claim_id": str(claim_id),
                    "dossier_id": dossier.dossier_id,
                    "escalation_code": escalation_code,
                    "escalation_reason": dossier.escalation_reason,
                    "status": target_status,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to publish {event_name} event for {claim_id}: {e}")

        logger.info(f"Escalated claim {claim_id} with code {escalation_code}: dossier {dossier.dossier_id}")
        return dossier

    async def get_voucher(self, claim_id: UUID) -> Optional[SettlementVoucherDTO]:
        claim = await self.claim_repo.get_by_id(claim_id)
        if claim and claim.settlement_voucher:
            return SettlementVoucherDTO.model_validate(claim.settlement_voucher)
        return None

    async def get_dossier(self, claim_id: UUID) -> Optional[HumanAdjusterDossierDTO]:
        claim = await self.claim_repo.get_by_id(claim_id)
        if not claim:
            return None
        policy = await self.policy_repo.get_by_id(claim.policy_id)
        registration_number = policy.registration_number if policy else "MH-REG-DEFAULT"

        esc_code = claim.escalation_code or "ESC-07"
        return self.dossier_bld.build_dossier(
            claim_id=claim_id,
            policy_id=claim.policy_id,
            registration_number=registration_number,
            escalation_code=esc_code,
            forensic_telemetry={
                "fast_fail": claim.fast_fail_telemetry,
                "continuity": claim.vehicle_continuity_telemetry,
                "dual_mask": claim.dual_mask_telemetry,
                "vlm": claim.vlm_inspection_telemetry,
            },
            actuarial_summary=claim.actuarial_estimate.get("summary") if claim.actuarial_estimate else None,
        )

