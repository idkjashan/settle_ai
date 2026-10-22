"""
app/domain/actuarial_pricing/orchestrator.py
Async Orchestrator coordinating DB lookups, fraud gates, OEM catalogue resolution,
deterministic IRDAI pricing calculation, autonomous financial ceiling enforcement,
NCB economic utility advisory, and PostgreSQL/Redis state persistence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.actuarial_pricing.calculator import ActuarialCalculator
from app.domain.actuarial_pricing.enums import (
    ActuarialEscalationCode,
    MaterialType,
    PaintType,
    RepairAction,
)
from app.domain.actuarial_pricing.exceptions import (
    ActuarialPricingError,
    Stage4CataloguePartNotFoundError,
    Stage4DoubleDippingFraudError,
    Stage4FinancialCeilingExceededError,
    Stage4PolicyDataInvalidError,
)
from app.domain.actuarial_pricing.ncb_advisor import NCBAdvisor
from app.domain.actuarial_pricing.rules import (
    AUTONOMOUS_CEILING_INR,
    calculate_denting_labor_multiplier,
    determine_repair_action,
    get_paint_type_multiplier,
    get_part_depreciation_rate,
    get_salvage_deduction_rate,
    quantize_inr,
    resolve_paint_overlap_factors,
)
from app.domain.actuarial_pricing.schemas import (
    ActuarialEstimateDTO,
    ActuarialLineItemDTO,
    ActuarialSummaryDTO,
    CashSettlementBandDTO,
    NCBAdvisoryDTO,
    PolicyPricingContextDTO,
)
from app.domain.vlm_damage_inspection.schemas import Stage4HandoffPayload, VerifiedDamagedPart
from app.infrastructure.cache.redis_manager import RedisManager
from app.infrastructure.db.models import Claim, InsuredPolicy, OemPart, UnrepairedClaim
from app.infrastructure.db.repositories import (
    ClaimRepository,
    OemRepository,
    PolicyRepository,
    UnrepairedClaimsRepository,
)

logger = logging.getLogger(__name__)


def _extract_attr(obj: Any, key: str, default: Any = None) -> Any:
    """Extract attribute or dictionary value safely."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class Stage4ActuarialOrchestrator:
    """
    End-to-end async orchestrator for Stage 4 Actuarial Pricing.
    Ingests Stage4HandoffPayload, performs pre-flight fraud check (ESC-03),
    queries OEM catalogue and applies segment fallbacks (ESC-09),
    computes deterministic statutory assessment, evaluates autonomous ceiling (ESC-08),
    computes NCB advisory, and persists results to PostgreSQL and Redis.
    """

    def __init__(
        self,
        session: AsyncSession,
        redis_manager: Optional[RedisManager] = None,
        calculator: Optional[ActuarialCalculator] = None,
        advisor: Optional[NCBAdvisor] = None,
        policy_repo: Optional[PolicyRepository] = None,
        oem_repo: Optional[OemRepository] = None,
        unrepaired_repo: Optional[UnrepairedClaimsRepository] = None,
        claim_repo: Optional[ClaimRepository] = None,
    ) -> None:
        self.session = session
        self.redis_manager = redis_manager
        self.calculator = calculator or ActuarialCalculator()
        self.advisor = advisor or NCBAdvisor()
        self.policy_repo = policy_repo or PolicyRepository(session)
        self.oem_repo = oem_repo or OemRepository(session)
        self.unrepaired_repo = unrepaired_repo or UnrepairedClaimsRepository(session)
        self.claim_repo = claim_repo or ClaimRepository(session)

    async def execute(
        self,
        handoff_payload: Stage4HandoffPayload | Dict[str, Any],
        target_stage: str = "STAGE_4_ACTUARIAL_PRICING",
        target_status: str = "PRICED_READY_FOR_NEGOTIATION",
    ) -> ActuarialEstimateDTO:
        """
        Execute full Stage 4 actuarial assessment pipeline.

        1. Ingest Stage4HandoffPayload and extract claim & policy identifiers.
        2. Query PolicyRepository to retrieve and validate InsuredPolicy.
        3. Pre-flight check: query UnrepairedClaimsRepository for double-dipping fraud (ESC-03).
        4. Query OemRepository for each damaged part; attempt segment fallback; raise ESC-09 if missing.
        5. Pass verified parts to ActuarialCalculator.calculate() with strict Decimal math.
        6. Enforce Autonomous Financial Ceiling: raise ESC-08 if gross repair > ₹75,000.00.
        7. Evaluate NCBAdvisor.evaluate() for customer economic utility guidance.
        8. Persist actuarial estimate in PostgreSQL (Claim.actuarial_estimate) and update status.
        9. Publish real-time Server-Sent Events (SSE) via RedisManager.
        10. Return ActuarialEstimateDTO.
        """
        # 1. Ingest identifiers
        raw_claim_id = _extract_attr(handoff_payload, "claim_id")
        claim_id = UUID(str(raw_claim_id)) if raw_claim_id is not None else UUID(int=0)
        policy_id = str(_extract_attr(handoff_payload, "policy_id", "") or "")
        registration_number = str(_extract_attr(handoff_payload, "registration_number", "") or "")

        logger.info(
            "Starting Stage 4 Actuarial Pricing for claim %s (policy_id: '%s', reg_no: '%s')",
            claim_id,
            policy_id,
            registration_number,
        )

        # 2. Fetch and Validate Policy
        policy = None
        if policy_id:
            policy = await self.policy_repo.get_by_id(policy_id)
        if not policy and registration_number:
            if hasattr(self.policy_repo, "get_by_registration"):
                policy = await self.policy_repo.get_by_registration(registration_number)

        if not policy:
            err_msg = f"Policy '{policy_id or registration_number}' not found in database."
            logger.error("Stage 4 validation failure: %s", err_msg)
            raise Stage4PolicyDataInvalidError(err_msg)

        # Build PolicyPricingContextDTO
        mfg_year = _extract_attr(policy, "manufacturing_year")
        if mfg_year is None:
            err_msg = f"Policy '{policy.policy_id}' is corrupt: missing manufacturing year."
            logger.error("Stage 4 validation failure: %s", err_msg)
            raise Stage4PolicyDataInvalidError(err_msg)

        raw_paint = _extract_attr(policy, "paint_type", "metallic")
        try:
            paint_type_enum = PaintType(str(raw_paint).lower()) if raw_paint else PaintType.METALLIC
        except ValueError:
            paint_type_enum = PaintType.METALLIC

        compulsory_deductible = Decimal(str(_extract_attr(policy, "compulsory_deductible_inr", "1000.00")))
        voluntary_deductible = Decimal(str(_extract_attr(policy, "voluntary_deductible_inr", "0.00")))
        estimated_ncb_loss = Decimal(str(_extract_attr(policy, "estimated_ncb_loss_inr", "3200.00")))
        zero_dep_addon = bool(_extract_attr(policy, "zero_dep_addon", True))
        engine_cc = _extract_attr(policy, "engine_cc", None)

        policy_context = PolicyPricingContextDTO(
            policy_id=policy.policy_id,
            registration_number=policy.registration_number,
            make=policy.make,
            model=policy.model,
            manufacturing_year=int(mfg_year),
            zero_dep_addon=zero_dep_addon,
            paint_type=paint_type_enum,
            compulsory_deductible_inr=compulsory_deductible,
            voluntary_deductible_inr=voluntary_deductible,
            estimated_ncb_loss_inr=estimated_ncb_loss,
            engine_cc=int(engine_cc) if engine_cc is not None else None,
        )

        verified_parts: List[VerifiedDamagedPart] = _extract_attr(handoff_payload, "verified_parts", []) or []
        part_keys = [str(_extract_attr(p, "canonical_part_key")) for p in verified_parts]

        # 3. Pre-flight Check: Double-Dipping Unrepaired Claims Fraud (ESC-03)
        fraud_part_key: Optional[str] = None
        if hasattr(self.unrepaired_repo, "has_unrepaired_claim"):
            for pk in part_keys:
                is_unrepaired = await self.unrepaired_repo.has_unrepaired_claim(
                    registration_number=policy.registration_number,
                    canonical_part_key=pk,
                )
                if is_unrepaired:
                    fraud_part_key = pk
                    break
        elif hasattr(self.unrepaired_repo, "get_unrepaired_claims"):
            unrepaired_records = await self.unrepaired_repo.get_unrepaired_claims(
                registration_number=policy.registration_number,
                canonical_part_keys=part_keys,
            )
            if unrepaired_records:
                fraud_part_key = str(_extract_attr(unrepaired_records[0], "canonical_part_key"))

        if fraud_part_key:
            esc_code = ActuarialEscalationCode.ESC_03.value
            logger.warning(
                "Double-dipping fraud detected on vehicle %s for part '%s' (%s). Escalating claim %s.",
                policy.registration_number,
                fraud_part_key,
                esc_code,
                claim_id,
            )
            await self.claim_repo.update_claim_stage(
                claim_id=claim_id,
                stage="ESCALATED",
                status="ESCALATED",
                escalation_code=esc_code,
                failure_codes=[esc_code],
            )
            if self.redis_manager:
                await self.redis_manager.publish_event(
                    claim_id=claim_id,
                    event_name="CLAIM_ESCALATED",
                    payload={
                        "claim_id": str(claim_id),
                        "escalation_code": esc_code,
                        "canonical_part_key": fraud_part_key,
                        "registration_number": policy.registration_number,
                        "reason": (
                            f"Prior unrepaired cash-in-lieu settlement detected for vehicle "
                            f"{policy.registration_number} on part '{fraud_part_key}'. "
                            f"Re-claiming unrepaired damage is prohibited."
                        ),
                    },
                )
            raise Stage4DoubleDippingFraudError(
                registration_number=policy.registration_number,
                canonical_part_key=fraud_part_key,
            )

        # 4. Resolve OEM Catalogue Parts with Segment Fallback (ESC-09)
        oem_catalog: Dict[str, OemPart] = {}
        for part in verified_parts:
            part_key = str(_extract_attr(part, "canonical_part_key"))
            part_record = await self.oem_repo.get_part(
                make=policy.make,
                model=policy.model,
                canonical_part_key=part_key,
            )
            if not part_record:
                part_record = await self._resolve_segment_fallback(policy, part_key)

            if not part_record:
                esc_code = ActuarialEscalationCode.ESC_09.value
                logger.error(
                    "Part '%s' for vehicle %s %s not found in OEM catalogue or segment fallback (%s). Escalating claim %s.",
                    part_key,
                    policy.make,
                    policy.model,
                    esc_code,
                    claim_id,
                )
                await self.claim_repo.update_claim_stage(
                    claim_id=claim_id,
                    stage="ESCALATED",
                    status="ESCALATED",
                    escalation_code=esc_code,
                    failure_codes=[esc_code],
                )
                if self.redis_manager:
                    await self.redis_manager.publish_event(
                        claim_id=claim_id,
                        event_name="CLAIM_ESCALATED",
                        payload={
                            "claim_id": str(claim_id),
                            "escalation_code": esc_code,
                            "canonical_part_key": part_key,
                            "make": policy.make,
                            "model": policy.model,
                            "reason": (
                                f"Part record for '{part_key}' ({policy.make} {policy.model}) was not "
                                f"found in OEM catalogue and no segment fallback is configured."
                            ),
                        },
                    )
                raise Stage4CataloguePartNotFoundError(
                    make=policy.make,
                    model=policy.model,
                    canonical_part_key=part_key,
                )
            oem_catalog[part_key] = part_record

        # 5. Deterministic Calculation & Financial Ceiling Enforcement (ESC-08)
        current_year = datetime.now(timezone.utc).year
        try:
            line_items, summary, settlement_band = self.calculator.calculate(
                policy_context=policy_context,
                verified_parts=verified_parts,
                oem_catalog=oem_catalog,
                current_year=current_year,
            )
        except Stage4FinancialCeilingExceededError as exc:
            esc_code = ActuarialEscalationCode.ESC_08.value
            gross_str = str(getattr(exc, "gross_amount_inr", "75000.00"))
            logger.warning(
                "Financial ceiling exceeded for claim %s: gross assessed repair ₹%s > limit ₹75,000.00 (%s). Escalating to human desk review.",
                claim_id,
                gross_str,
                esc_code,
            )

            # Build and attach preliminary estimate if not present
            if getattr(exc, "preliminary_estimate", None) is None:
                try:
                    prelim_est = self._build_preliminary_estimate(
                        claim_id=claim_id,
                        policy=policy,
                        policy_context=policy_context,
                        verified_parts=verified_parts,
                        oem_catalog=oem_catalog,
                        gross_amount_inr=gross_str,
                    )
                    exc.preliminary_estimate = prelim_est
                    exc.estimate = prelim_est
                except Exception as build_err:
                    logger.debug("Could not construct preliminary estimate: %s", build_err)

            prelim_dict = None
            if getattr(exc, "preliminary_estimate", None) is not None:
                stored = exc.preliminary_estimate
                if hasattr(stored, "to_dict"):
                    prelim_dict = stored.to_dict()
                elif hasattr(stored, "model_dump"):
                    prelim_dict = stored.model_dump(mode="json")

            # Persist escalation state in PostgreSQL
            await self.claim_repo.update_claim_stage(
                claim_id=claim_id,
                stage="ESCALATED",
                status="ESCALATED_HUMAN_REVIEW",
                escalation_code=esc_code,
                failure_codes=[esc_code],
                telemetry_update=prelim_dict,
                telemetry_column="actuarial_estimate" if prelim_dict else None,
            )

            # Emit Redis SSE event
            if self.redis_manager:
                await self.redis_manager.publish_event(
                    claim_id=claim_id,
                    event_name="CLAIM_ESCALATED",
                    payload={
                        "claim_id": str(claim_id),
                        "escalation_code": esc_code,
                        "gross_garage_repair_inr": gross_str,
                        "reason": (
                            f"Gross assessed repair amount of ₹{gross_str} exceeds the autonomous "
                            f"cash-settlement ceiling of ₹75000.00. Claim escalated to desk surveyor."
                        ),
                    },
                )
            raise exc

        # 6. Evaluate No Claim Bonus (NCB) Economic Utility Advisory
        ncb_advisory: NCBAdvisoryDTO = self.advisor.evaluate(
            net_claim_liability_inr=summary.net_claim_liability_inr,
            estimated_ncb_loss_inr=policy_context.estimated_ncb_loss_inr,
        )

        # 7. Construct Master Downstream DTO
        estimate = ActuarialEstimateDTO(
            claim_id=claim_id,
            policy_id=policy.policy_id,
            registration_number=policy.registration_number,
            vehicle_make=policy.make,
            vehicle_model=policy.model,
            vehicle_year=policy.manufacturing_year,
            calculation_timestamp=datetime.now(timezone.utc),
            is_zero_dep_active=policy_context.zero_dep_addon,
            is_ceiling_breached=False,
            escalation_code=None,
            line_items=line_items,
            summary=summary,
            settlement_band=settlement_band,
            ncb_advisory=ncb_advisory,
        )

        # 8. Persist to PostgreSQL Claim Record
        estimate_dict = estimate.to_dict() if hasattr(estimate, "to_dict") else estimate.model_dump(mode="json")
        await self.claim_repo.update_claim_stage(
            claim_id=claim_id,
            stage=target_stage,
            status=target_status,
            telemetry_update=estimate_dict,
            telemetry_column="actuarial_estimate",
        )

        # 9. Publish Real-Time Redis SSE Events
        if self.redis_manager:
            rec_val = (
                ncb_advisory.recommendation.value
                if hasattr(ncb_advisory.recommendation, "value")
                else str(ncb_advisory.recommendation)
            )
            sse_payload = {
                "claim_id": str(claim_id),
                "gross_garage_repair_inr": str(summary.gross_garage_repair_inr),
                "net_claim_liability_inr": str(summary.net_claim_liability_inr),
                "initial_offer_inr": str(settlement_band.initial_offer_inr),
                "target_settlement_inr": str(settlement_band.target_settlement_inr),
                "walkaway_cap_inr": str(settlement_band.walkaway_cap_inr),
                "ncb_recommendation": rec_val,
            }
            # Spec-mandated event
            await self.redis_manager.publish_event(
                claim_id=claim_id,
                event_name="STAGE_4_PRICING_COMPLETED",
                payload=sse_payload,
            )
            # LLD Section 5.2 event
            await self.redis_manager.publish_event(
                claim_id=claim_id,
                event_name="ACTUARIAL_PRICING_COMPLETED",
                payload=sse_payload,
            )

        logger.info(
            "Stage 4 pricing completed successfully for claim %s: gross ₹%s, net liability ₹%s, initial offer ₹%s",
            claim_id,
            summary.gross_garage_repair_inr,
            summary.net_claim_liability_inr,
            settlement_band.initial_offer_inr,
        )
        return estimate

    async def _resolve_segment_fallback(
        self,
        policy: InsuredPolicy | PolicyPricingContextDTO,
        canonical_part_key: str,
    ) -> Optional[OemPart]:
        """
        Attempts to resolve an unlisted part by inspecting segment baseline averages
        and applying a 10% statutory safety buffer.
        """
        make = policy.make
        model = policy.model
        segment = self._infer_vehicle_segment(make, model)

        # 1. Direct repository segment fallback if available
        if hasattr(self.oem_repo, "get_segment_fallback"):
            fb = await self.oem_repo.get_segment_fallback(segment, canonical_part_key)
            if fb:
                return self._create_buffered_part(fb, make, model, canonical_part_key)

        # 2. Known models within the same vehicle segment
        segment_models = self._get_models_for_segment(segment)
        for seg_make, seg_model in segment_models:
            part = await self.oem_repo.get_part(
                make=seg_make,
                model=seg_model,
                canonical_part_key=canonical_part_key,
            )
            if part:
                return self._create_buffered_part(part, make, model, canonical_part_key)

        # 3. Query PostgreSQL for any catalogue part matching canonical_part_key
        try:
            stmt = select(OemPart).where(OemPart.canonical_part_key == canonical_part_key).limit(1)
            result = await self.session.execute(stmt)
            generic_part = result.scalar_one_or_none()
            if generic_part:
                return self._create_buffered_part(generic_part, make, model, canonical_part_key)
        except Exception as exc:
            logger.debug("Database generic part fallback query failed: %s", exc)

        return None

    @staticmethod
    def _create_buffered_part(
        template: Any,
        target_make: str,
        target_model: str,
        canonical_part_key: str,
    ) -> OemPart:
        """Inject 10% safety buffer onto segment fallback baseline."""
        buffer = Decimal("1.10")
        base_cost = Decimal(str(_extract_attr(template, "oem_part_cost_inr", "0.00")))
        rr_labour = Decimal(str(_extract_attr(template, "rr_labour_inr", "0.00")))
        dent_labour = Decimal(str(_extract_attr(template, "denting_base_labour_inr", "0.00")))
        paint_cost = Decimal(str(_extract_attr(template, "full_panel_paint_inr", "0.00")))
        pdr_flat = Decimal(str(_extract_attr(template, "pdr_or_polish_flat_inr", "0.00")))

        return OemPart(
            make=target_make,
            model=target_model,
            canonical_part_key=canonical_part_key,
            display_part_name=str(_extract_attr(template, "display_part_name", canonical_part_key.replace("_", " ").title())),
            oem_part_number=f"SEG-FB-{_extract_attr(template, 'oem_part_number', canonical_part_key.upper())}",
            part_material=str(_extract_attr(template, "part_material", "metal")),
            depreciation_rate_non_zero_dep=Decimal("0.00"),
            oem_part_cost_inr=quantize_inr(base_cost * buffer),
            rr_labour_inr=quantize_inr(rr_labour * buffer),
            denting_base_labour_inr=quantize_inr(dent_labour * buffer),
            full_panel_paint_inr=quantize_inr(paint_cost * buffer),
            pdr_or_polish_flat_inr=quantize_inr(pdr_flat * buffer),
            is_repairable=bool(_extract_attr(template, "is_repairable", True)),
            is_safety_critical=bool(_extract_attr(template, "is_safety_critical", False)),
        )

    @staticmethod
    def _infer_vehicle_segment(make: str, model: str) -> str:
        """Categorize vehicle into market segment for fallback median pricing."""
        m_lower = model.lower()
        make_lower = make.lower()
        if any(k in m_lower for k in ["swift", "i10", "i20", "wagonr", "baleno", "altroz", "tiago", "polo"]):
            return "HATCHBACK"
        if any(k in m_lower for k in ["city", "verna", "ciaz", "dzire", "amaze", "slavia", "virtus"]):
            return "SEDAN"
        if any(k in m_lower for k in ["creta", "seltos", "brezza", "nexon", "venue", "sonet", "kushaq", "taigun"]):
            return "COMPACT_SUV"
        if any(k in m_lower for k in ["fortuner", "harrier", "safari", "xuv700", "scorpio", "hector"]):
            return "MIDSIZE_SUV"
        if any(k in make_lower for k in ["bmw", "mercedes", "audi", "volvo", "jaguar", "porsche", "land rover"]):
            return "LUXURY"
        return "COMPACT_SUV"

    @staticmethod
    def _get_models_for_segment(segment: str) -> List[Tuple[str, str]]:
        """Known seeded models for each vehicle segment."""
        mapping = {
            "HATCHBACK": [("Maruti", "Swift"), ("Hyundai", "i20")],
            "SEDAN": [("Honda", "City"), ("Hyundai", "Verna")],
            "COMPACT_SUV": [("Hyundai", "Creta"), ("Tata", "Nexon"), ("Kia", "Seltos")],
            "MIDSIZE_SUV": [("Toyota", "Fortuner"), ("Mahindra", "XUV700")],
            "LUXURY": [("BMW", "X3"), ("Mercedes", "C-Class")],
        }
        return mapping.get(segment, [("Hyundai", "Creta")])

    def _build_preliminary_estimate(
        self,
        claim_id: UUID,
        policy: InsuredPolicy,
        policy_context: PolicyPricingContextDTO,
        verified_parts: List[VerifiedDamagedPart],
        oem_catalog: Dict[str, OemPart],
        gross_amount_inr: str,
    ) -> ActuarialEstimateDTO:
        """
        Construct a preliminary ActuarialEstimateDTO prior to escalation,
        ensuring audit trail preservation on autonomous ceiling breaches (ESC-08).
        """
        current_year = datetime.now(timezone.utc).year
        vehicle_age = max(0.0, float(current_year - policy_context.manufacturing_year))
        paint_multiplier = get_paint_type_multiplier(policy_context.paint_type)

        # First pass: paintable panels
        paintable_panels: List[Tuple[str, Decimal]] = []
        for part in verified_parts:
            part_key = str(_extract_attr(part, "canonical_part_key"))
            oem = oem_catalog[part_key]
            is_rep = bool(_extract_attr(oem, "is_repairable", True)) and bool(
                _extract_attr(part, "is_repairable", True)
            )
            raw_dg = _extract_attr(part, "depth_grade")
            depth_val = raw_dg.value if hasattr(raw_dg, "value") else str(raw_dg)
            action = determine_repair_action(
                is_repairable=is_rep,
                depth_grade=depth_val,
                iop_ratio=float(_extract_attr(part, "final_iop_ratio", 0.0)),
            )
            needs_paint = False
            paint_cost = Decimal(str(_extract_attr(oem, "full_panel_paint_inr", "0.00")))
            if action == RepairAction.REPLACE and paint_cost > Decimal("0.00"):
                needs_paint = True
            elif action == RepairAction.REPAIR and depth_val in ("L2_BASECOAT_SCRATCH", "L4_CREASED_DENT"):
                if paint_cost > Decimal("0.00"):
                    needs_paint = True
            if needs_paint:
                paintable_panels.append((part_key, paint_cost))

        overlap_map = dict(resolve_paint_overlap_factors(paintable_panels))

        # Second pass: line items
        line_items: List[ActuarialLineItemDTO] = []
        for part in verified_parts:
            part_key = str(_extract_attr(part, "canonical_part_key"))
            oem = oem_catalog[part_key]
            mat_str = str(_extract_attr(oem, "part_material", "metal"))
            try:
                material = MaterialType(mat_str.lower())
            except ValueError:
                material = MaterialType.METAL

            is_rep = bool(_extract_attr(oem, "is_repairable", True)) and bool(
                _extract_attr(part, "is_repairable", True)
            )
            raw_dg = _extract_attr(part, "depth_grade")
            depth_val = raw_dg.value if hasattr(raw_dg, "value") else str(raw_dg)
            iop_ratio = float(_extract_attr(part, "final_iop_ratio", 0.0))
            action = determine_repair_action(
                is_repairable=is_rep,
                depth_grade=depth_val,
                iop_ratio=iop_ratio,
            )

            if action == RepairAction.REPLACE:
                base_part_cost = Decimal(str(_extract_attr(oem, "oem_part_cost_inr", "0.00")))
                dep_rate = get_part_depreciation_rate(
                    material=material,
                    vehicle_age_years=vehicle_age,
                    is_zero_dep=policy_context.zero_dep_addon,
                )
                dep_amount = quantize_inr(base_part_cost * dep_rate)
                net_part_cost = quantize_inr(base_part_cost - dep_amount)
                salvage_rate = get_salvage_deduction_rate(material, action)
                salvage_deduction = quantize_inr(net_part_cost * salvage_rate)
                rr_labour = Decimal(str(_extract_attr(oem, "rr_labour_inr", "0.00")))
                denting_labour = Decimal("0.00")
                pdr_flat = Decimal("0.00")
            else:
                base_part_cost = Decimal("0.00")
                dep_rate = Decimal("0.00")
                dep_amount = Decimal("0.00")
                net_part_cost = Decimal("0.00")
                salvage_deduction = Decimal("0.00")
                rr_labour = Decimal("0.00")
                if depth_val in ("L1_SURFACE_SCUFF", "L3_SHALLOW_DENT_PDR"):
                    pdr_flat = Decimal(str(_extract_attr(oem, "pdr_or_polish_flat_inr", "0.00")))
                    denting_labour = Decimal("0.00")
                elif depth_val == "L4_CREASED_DENT":
                    pdr_flat = Decimal("0.00")
                    gamma_iop = calculate_denting_labor_multiplier(iop_ratio)
                    denting_labour = quantize_inr(
                        Decimal(str(_extract_attr(oem, "denting_base_labour_inr", "0.00"))) * gamma_iop
                    )
                else:
                    pdr_flat = Decimal("0.00")
                    denting_labour = Decimal("0.00")

            overlap_factor = overlap_map.get(part_key, Decimal("0.00"))
            if overlap_factor > Decimal("0.00"):
                base_paint = Decimal(str(_extract_attr(oem, "full_panel_paint_inr", "0.00")))
                final_paint = quantize_inr(base_paint * paint_multiplier * overlap_factor)
            else:
                base_paint = Decimal("0.00")
                final_paint = Decimal("0.00")

            pre_tax_total = quantize_inr(net_part_cost + rr_labour + denting_labour + pdr_flat + final_paint)
            gst_amount = quantize_inr(pre_tax_total * Decimal("0.18"))
            gross_line_item = quantize_inr(pre_tax_total + gst_amount)

            line_items.append(
                ActuarialLineItemDTO(
                    canonical_part_key=part_key,
                    display_part_name=str(_extract_attr(oem, "display_part_name", part_key)),
                    oem_part_number=str(_extract_attr(oem, "oem_part_number", "UNKNOWN")),
                    material=material,
                    action=action,
                    depth_grade=depth_val,
                    iop_ratio=iop_ratio,
                    base_part_cost_inr=base_part_cost,
                    depreciation_rate_pct=quantize_inr(dep_rate * Decimal("100.0")),
                    depreciation_amount_inr=dep_amount,
                    net_part_cost_inr=net_part_cost,
                    salvage_deduction_inr=salvage_deduction,
                    rr_labour_inr=rr_labour,
                    denting_labour_inr=denting_labour,
                    pdr_polish_flat_inr=pdr_flat,
                    base_paint_inr=base_paint,
                    paint_multiplier=paint_multiplier,
                    paint_overlap_discount=quantize_inr((Decimal("1.00") - overlap_factor) * Decimal("100.0")),
                    final_paint_inr=final_paint,
                    pre_tax_total_inr=pre_tax_total,
                    gst_amount_inr=gst_amount,
                    gross_line_item_total_inr=gross_line_item,
                )
            )

        # Summary
        tot_gross_parts = sum((item.base_part_cost_inr for item in line_items), Decimal("0.00"))
        tot_dep = sum((item.depreciation_amount_inr for item in line_items), Decimal("0.00"))
        tot_net_parts = sum((item.net_part_cost_inr for item in line_items), Decimal("0.00"))
        tot_labour = sum((item.rr_labour_inr + item.denting_labour_inr + item.pdr_polish_flat_inr for item in line_items), Decimal("0.00"))
        tot_paint = sum((item.final_paint_inr for item in line_items), Decimal("0.00"))
        pre_tax_subtotal = quantize_inr(tot_net_parts + tot_labour + tot_paint)
        tot_gst = quantize_inr(pre_tax_subtotal * Decimal("0.18"))
        gross_garage_repair = Decimal(gross_amount_inr)
        tot_salvage = sum((item.salvage_deduction_inr for item in line_items), Decimal("0.00"))

        compulsory_deductible = policy_context.compulsory_deductible_inr
        voluntary_deductible = policy_context.voluntary_deductible_inr
        tot_deductibles = quantize_inr(compulsory_deductible + voluntary_deductible)

        payable_before = quantize_inr(gross_garage_repair - tot_salvage)
        net_claim_liability = quantize_inr(max(Decimal("0.00"), payable_before - tot_deductibles))

        summary = ActuarialSummaryDTO(
            total_gross_parts_inr=tot_gross_parts,
            total_depreciation_inr=tot_dep,
            total_net_parts_inr=tot_net_parts,
            total_labour_inr=tot_labour,
            total_paint_inr=tot_paint,
            pre_tax_subtotal_inr=pre_tax_subtotal,
            total_gst_inr=tot_gst,
            gross_garage_repair_inr=gross_garage_repair,
            total_salvage_deduction_inr=tot_salvage,
            compulsory_deductible_inr=compulsory_deductible,
            voluntary_deductible_inr=voluntary_deductible,
            total_deductible_inr=tot_deductibles,
            net_claim_liability_inr=net_claim_liability,
        )

        settlement_band = CashSettlementBandDTO(
            initial_offer_inr=quantize_inr(net_claim_liability * Decimal("0.75")),
            target_settlement_inr=quantize_inr(net_claim_liability * Decimal("0.85")),
            walkaway_cap_inr=quantize_inr(min(AUTONOMOUS_CEILING_INR, net_claim_liability * Decimal("0.95"))),
            financial_ceiling_inr=AUTONOMOUS_CEILING_INR,
        )

        ncb_advisory = self.advisor.evaluate(
            net_claim_liability_inr=net_claim_liability,
            estimated_ncb_loss_inr=policy_context.estimated_ncb_loss_inr,
        )

        return ActuarialEstimateDTO(
            claim_id=claim_id,
            policy_id=policy.policy_id,
            registration_number=policy.registration_number,
            vehicle_make=policy.make,
            vehicle_model=policy.model,
            vehicle_year=policy.manufacturing_year,
            calculation_timestamp=datetime.now(timezone.utc),
            is_zero_dep_active=policy_context.zero_dep_addon,
            is_ceiling_breached=True,
            escalation_code=ActuarialEscalationCode.ESC_08.value,
            line_items=line_items,
            summary=summary,
            settlement_band=settlement_band,
            ncb_advisory=ncb_advisory,
        )
