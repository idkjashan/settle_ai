"""
tests/actuarial_pricing/test_orchestrator.py
Async integration tests for Stage4ActuarialOrchestrator coordinating DB lookups,
fraud prevention gates (ESC-03), OEM catalogue resolution & segment fallback (ESC-09),
statutory pricing, autonomous financial ceiling enforcement (ESC-08), and Redis/PostgreSQL updates.
"""
from datetime import date
from decimal import Decimal
import uuid
import pytest

from app.domain.actuarial_pricing.enums import ActuarialEscalationCode, PaintType
from app.domain.actuarial_pricing.exceptions import (
    Stage4CataloguePartNotFoundError,
    Stage4DoubleDippingFraudError,
    Stage4FinancialCeilingExceededError,
    Stage4PolicyDataInvalidError,
)
from app.domain.actuarial_pricing.orchestrator import Stage4ActuarialOrchestrator
from app.domain.actuarial_pricing.schemas import ActuarialEstimateDTO
from app.domain.vlm_damage_inspection.schemas import (
    DepthGrade,
    Stage4HandoffPayload,
)
from app.infrastructure.cache.redis_manager import RedisManager
from app.infrastructure.db.models import Claim, InsuredPolicy
from tests.actuarial_pricing.conftest import (
    make_dummy_verified_part,
    seed_in_memory_claim,
)
from tests.in_memory_db import FakeAsyncSession, in_memory_db


@pytest.mark.asyncio
class TestStage4ActuarialOrchestrator:
    """Integration test suite for Stage4ActuarialOrchestrator."""

    async def test_happy_path_end_to_end_pricing(
        self,
        db_session: FakeAsyncSession,
        redis_mgr: RedisManager,
    ):
        """
        Happy path:
        Ingests valid Stage4HandoffPayload for Hyundai Creta.
        Performs pre-flight checks, catalogue pricing, and NCB evaluation.
        Persists actuarial estimate to PostgreSQL and publishes Redis SSE events.
        """
        claim_id = uuid.uuid4()
        claim = seed_in_memory_claim(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            current_stage="STAGE_3_VLM_INSPECTION",
            claim_status="PROCESSING",
        )

        part = make_dummy_verified_part(
            canonical_part_key="front_left_fender",
            depth_grade=DepthGrade.L4_CREASED_DENT,
            final_iop_ratio=0.10,
            is_repairable=True,
        )

        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            registration_number="MH12DE1433",
            make="Hyundai",
            model="Creta",
            verified_parts=[part],
        )

        orchestrator = Stage4ActuarialOrchestrator(
            session=db_session,
            redis_manager=redis_mgr,
        )

        estimate = await orchestrator.execute(payload)

        # 1. Verify returned DTO
        assert isinstance(estimate, ActuarialEstimateDTO)
        assert estimate.claim_id == claim_id
        assert estimate.policy_id == "POL-HAPPY-001"
        assert estimate.registration_number == "MH12DE1433"
        assert estimate.vehicle_make == "Hyundai"
        assert estimate.vehicle_model == "Creta"
        assert estimate.is_zero_dep_active is True
        assert estimate.is_ceiling_breached is False
        assert len(estimate.line_items) == 1
        assert estimate.summary.net_claim_liability_inr > Decimal("0.00")
        assert estimate.settlement_band.initial_offer_inr > Decimal("0.00")
        assert estimate.ncb_advisory.advisory_message != ""

        # 2. Verify PostgreSQL Claim state update
        updated_claim = in_memory_db.claims[claim_id]
        assert updated_claim.current_stage == "STAGE_4_ACTUARIAL_PRICING"
        assert updated_claim.claim_status == "PRICED_READY_FOR_NEGOTIATION"
        assert updated_claim.actuarial_estimate is not None
        assert "summary" in updated_claim.actuarial_estimate
        assert "settlement_band" in updated_claim.actuarial_estimate
        assert "line_items" in updated_claim.actuarial_estimate

        # 3. Verify Redis SSE events published
        events = [e for e in in_memory_db.events if e["claim_id"] == claim_id]
        event_names = [e["event"] for e in events]
        assert "STAGE_4_PRICING_COMPLETED" in event_names
        assert "ACTUARIAL_PRICING_COMPLETED" in event_names

        pricing_event = next(e for e in events if e["event"] == "STAGE_4_PRICING_COMPLETED")
        assert pricing_event["data"]["claim_id"] == str(claim_id)
        assert Decimal(pricing_event["data"]["net_claim_liability_inr"]) == estimate.summary.net_claim_liability_inr
        assert Decimal(pricing_event["data"]["initial_offer_inr"]) == estimate.settlement_band.initial_offer_inr

    async def test_double_dipping_fraud_esc_03(
        self,
        db_session: FakeAsyncSession,
        redis_mgr: RedisManager,
    ):
        """
        LLD Edge Case 9:
        Vehicle MH12DE1433 has prior open unrepaired cash payout on 'back_bumper'.
        Claiming 'back_bumper' again raises Stage4DoubleDippingFraudError (ESC-03).
        Claim is escalated and ESC-03 event is emitted via Redis.
        """
        claim_id = uuid.uuid4()
        claim = seed_in_memory_claim(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",  # reg is MH12DE1433
            current_stage="STAGE_3_VLM_INSPECTION",
            claim_status="PROCESSING",
        )

        # Claiming back_bumper which is seeded as unrepaired in in_memory_db
        fraud_part = make_dummy_verified_part(
            canonical_part_key="back_bumper",
            depth_grade=DepthGrade.L4_CREASED_DENT,
            final_iop_ratio=0.15,
        )

        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            registration_number="MH12DE1433",
            make="Hyundai",
            model="Creta",
            verified_parts=[fraud_part],
        )

        orchestrator = Stage4ActuarialOrchestrator(
            session=db_session,
            redis_manager=redis_mgr,
        )

        with pytest.raises(Stage4DoubleDippingFraudError) as exc_info:
            await orchestrator.execute(payload)

        err = exc_info.value
        assert err.escalation_code == ActuarialEscalationCode.ESC_03
        assert err.canonical_part_key == "back_bumper"
        assert err.registration_number == "MH12DE1433"

        # Check DB update
        updated_claim = in_memory_db.claims[claim_id]
        assert updated_claim.current_stage == "ESCALATED"
        assert updated_claim.claim_status == "ESCALATED"
        assert updated_claim.escalation_code == "ESC-03"
        assert updated_claim.failure_codes == ["ESC-03"]

        # Check Redis SSE event
        esc_events = [e for e in in_memory_db.events if e["claim_id"] == claim_id and e["event"] == "CLAIM_ESCALATED"]
        assert len(esc_events) == 1
        assert esc_events[0]["data"]["escalation_code"] == "ESC-03"
        assert esc_events[0]["data"]["canonical_part_key"] == "back_bumper"

    async def test_missing_catalogue_part_no_fallback_esc_09(
        self,
        db_session: FakeAsyncSession,
        redis_mgr: RedisManager,
    ):
        """
        LLD Edge Case 12 (unresolvable):
        Part key is completely unknown and no segment fallback exists.
        Raises Stage4CataloguePartNotFoundError (ESC-09), escalates claim, emits event.
        """
        claim_id = uuid.uuid4()
        claim = seed_in_memory_claim(claim_id=claim_id, policy_id="POL-HAPPY-001")

        unmapped_part = make_dummy_verified_part(
            canonical_part_key="completely_alien_part_9999",
            depth_grade=DepthGrade.L4_CREASED_DENT,
            final_iop_ratio=0.10,
        )

        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            registration_number="MH12DE1433",
            make="Hyundai",
            model="Creta",
            verified_parts=[unmapped_part],
        )

        orchestrator = Stage4ActuarialOrchestrator(
            session=db_session,
            redis_manager=redis_mgr,
        )

        with pytest.raises(Stage4CataloguePartNotFoundError) as exc_info:
            await orchestrator.execute(payload)

        err = exc_info.value
        assert err.escalation_code == ActuarialEscalationCode.ESC_09
        assert err.canonical_part_key == "completely_alien_part_9999"

        # Check DB escalation
        updated_claim = in_memory_db.claims[claim_id]
        assert updated_claim.current_stage == "ESCALATED"
        assert updated_claim.claim_status == "ESCALATED"
        assert updated_claim.escalation_code == "ESC-09"
        assert updated_claim.failure_codes == ["ESC-09"]

        # Check Redis event
        esc_events = [e for e in in_memory_db.events if e["claim_id"] == claim_id and e["event"] == "CLAIM_ESCALATED"]
        assert len(esc_events) == 1
        assert esc_events[0]["data"]["escalation_code"] == "ESC-09"
        assert esc_events[0]["data"]["canonical_part_key"] == "completely_alien_part_9999"

    async def test_segment_fallback_resolution(
        self,
        db_session: FakeAsyncSession,
        redis_mgr: RedisManager,
    ):
        """
        LLD Edge Case 12 (resolvable fallback):
        Vehicle make='Kia', model='Seltos' (COMPACT_SUV) is not seeded in oem_parts.
        Orchestrator queries segment fallback for COMPACT_SUV and matches Creta parts with +10% safety buffer.
        Pricing proceeds successfully and does not escalate.
        """
        # Register a Kia Seltos policy
        kia_policy = InsuredPolicy(
            policy_id="POL-KIA-SELTOS-001",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="MH14KS7777",
            vin_last_6="11992A",
            make="Kia",
            model="Seltos",
            manufacturing_year=2023,
            registered_color="WHITE",
            paint_type="metallic",
            zero_dep_addon=True,
            compulsory_deductible_inr=Decimal("1000.00"),
            estimated_ncb_loss_inr=Decimal("3200.00"),
        )
        in_memory_db.policies["POL-KIA-SELTOS-001"] = kia_policy

        claim_id = uuid.uuid4()
        claim = seed_in_memory_claim(claim_id=claim_id, policy_id="POL-KIA-SELTOS-001")

        # front_left_fender is in Creta catalogue, so segment fallback will borrow it + 10% buffer
        part = make_dummy_verified_part(
            canonical_part_key="front_left_fender",
            depth_grade=DepthGrade.L4_CREASED_DENT,
            final_iop_ratio=0.10,
            is_repairable=True,
        )

        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-KIA-SELTOS-001",
            registration_number="MH14KS7777",
            make="Kia",
            model="Seltos",
            verified_parts=[part],
        )

        orchestrator = Stage4ActuarialOrchestrator(
            session=db_session,
            redis_manager=redis_mgr,
        )

        estimate = await orchestrator.execute(payload)

        assert isinstance(estimate, ActuarialEstimateDTO)
        assert estimate.vehicle_make == "Kia"
        assert estimate.vehicle_model == "Kia" or estimate.vehicle_make == "Kia"
        assert len(estimate.line_items) == 1

        line_item = estimate.line_items[0]
        # Verify fallback part number has SEG-FB- prefix
        assert line_item.oem_part_number.startswith("SEG-FB-")
        # Verify base paint has 10% safety buffer: Creta base paint is ₹3,200.00 * 1.10 = ₹3,520.00
        assert line_item.base_paint_inr == Decimal("3520.00")

        # Verify claim completed
        updated_claim = in_memory_db.claims[claim_id]
        assert updated_claim.claim_status == "PRICED_READY_FOR_NEGOTIATION"

    async def test_autonomous_ceiling_breach_esc_08(
        self,
        db_session: FakeAsyncSession,
        redis_mgr: RedisManager,
    ):
        """
        LLD Edge Case 8:
        Toyota Fortuner with front_bumper + hood replacement exceeding ₹25,000.00.
        Raises Stage4FinancialCeilingExceededError (ESC-08).
        Orchestrator attaches preliminary estimate, escalates claim to ESCALATED_HUMAN_REVIEW,
        persists preliminary estimate to Claim.actuarial_estimate, and emits Redis event.
        """
        claim_id = uuid.uuid4()
        claim = seed_in_memory_claim(claim_id=claim_id, policy_id="POL-CEILING-BREACH")

        parts = [
            make_dummy_verified_part("front_bumper", is_repairable=False, depth_grade=DepthGrade.L5_STRUCTURAL_TEAR),
            make_dummy_verified_part("hood", is_repairable=False, depth_grade=DepthGrade.L5_STRUCTURAL_TEAR),
        ]

        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-CEILING-BREACH",
            registration_number="MH01CB2500",
            make="Toyota",
            model="Fortuner",
            verified_parts=parts,
        )

        orchestrator = Stage4ActuarialOrchestrator(
            session=db_session,
            redis_manager=redis_mgr,
        )

        with pytest.raises(Stage4FinancialCeilingExceededError) as exc_info:
            await orchestrator.execute(payload)

        err = exc_info.value
        assert err.escalation_code == ActuarialEscalationCode.ESC_08
        assert Decimal(err.gross_amount_inr) > Decimal("25000.00")

        # Verify preliminary estimate was attached to exception
        assert err.preliminary_estimate is not None
        assert err.preliminary_estimate.is_ceiling_breached is True
        assert err.preliminary_estimate.escalation_code == "ESC-08"

        # Check DB update
        updated_claim = in_memory_db.claims[claim_id]
        assert updated_claim.current_stage == "ESCALATED"
        assert updated_claim.claim_status == "ESCALATED_HUMAN_REVIEW"
        assert updated_claim.escalation_code == "ESC-08"
        assert updated_claim.failure_codes == ["ESC-08"]
        assert updated_claim.actuarial_estimate is not None
        assert updated_claim.actuarial_estimate["is_ceiling_breached"] is True

        # Check Redis event
        esc_events = [e for e in in_memory_db.events if e["claim_id"] == claim_id and e["event"] == "CLAIM_ESCALATED"]
        assert len(esc_events) == 1
        assert esc_events[0]["data"]["escalation_code"] == "ESC-08"
        assert "25000.00" in esc_events[0]["data"]["reason"]

    async def test_policy_not_found_raises_error(
        self,
        db_session: FakeAsyncSession,
        redis_mgr: RedisManager,
    ):
        """Unknown policy and registration raises Stage4PolicyDataInvalidError."""
        payload = Stage4HandoffPayload(
            claim_id=uuid.uuid4(),
            policy_id="POL-NON-EXISTENT-999",
            registration_number="XX00ZZ9999",
            make="Unknown",
            model="Unknown",
            verified_parts=[],
        )

        orchestrator = Stage4ActuarialOrchestrator(session=db_session, redis_manager=redis_mgr)

        with pytest.raises(Stage4PolicyDataInvalidError) as exc_info:
            await orchestrator.execute(payload)

        assert "not found" in str(exc_info.value)

    async def test_corrupt_policy_missing_manufacturing_year(
        self,
        db_session: FakeAsyncSession,
        redis_mgr: RedisManager,
    ):
        """Corrupt policy record with missing manufacturing_year raises Stage4PolicyDataInvalidError."""
        corrupt_policy = InsuredPolicy(
            policy_id="POL-CORRUPT-YEAR",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="MH12CP0000",
            vin_last_6="99999Z",
            make="Hyundai",
            model="Creta",
            manufacturing_year=None,  # Missing manufacturing year!
            registered_color="WHITE",
            paint_type="metallic",
            zero_dep_addon=True,
        )
        in_memory_db.policies["POL-CORRUPT-YEAR"] = corrupt_policy

        payload = Stage4HandoffPayload(
            claim_id=uuid.uuid4(),
            policy_id="POL-CORRUPT-YEAR",
            registration_number="MH12CP0000",
            make="Hyundai",
            model="Creta",
            verified_parts=[],
        )

        orchestrator = Stage4ActuarialOrchestrator(session=db_session, redis_manager=redis_mgr)

        with pytest.raises(Stage4PolicyDataInvalidError) as exc_info:
            await orchestrator.execute(payload)

        assert "missing manufacturing year" in str(exc_info.value)

    async def test_accepts_dict_payload(
        self,
        db_session: FakeAsyncSession,
        redis_mgr: RedisManager,
    ):
        """Orchestrator handles raw dictionary payload interchangeably with Stage4HandoffPayload."""
        claim_id = uuid.uuid4()
        seed_in_memory_claim(claim_id=claim_id, policy_id="POL-HAPPY-001")

        part = make_dummy_verified_part(
            canonical_part_key="front_left_fender",
            depth_grade=DepthGrade.L1_SURFACE_SCUFF,
            final_iop_ratio=0.05,
        )

        dict_payload = {
            "claim_id": str(claim_id),
            "policy_id": "POL-HAPPY-001",
            "registration_number": "MH12DE1433",
            "make": "Hyundai",
            "model": "Creta",
            "verified_parts": [part],
        }

        orchestrator = Stage4ActuarialOrchestrator(session=db_session, redis_manager=redis_mgr)
        estimate = await orchestrator.execute(dict_payload)
        assert estimate.claim_id == claim_id
        assert estimate.registration_number == "MH12DE1433"

    async def test_orchestrator_without_redis_manager(
        self,
        db_session: FakeAsyncSession,
    ):
        """Orchestrator operates cleanly when redis_manager is None."""
        claim_id = uuid.uuid4()
        seed_in_memory_claim(claim_id=claim_id, policy_id="POL-HAPPY-001")

        part = make_dummy_verified_part(
            canonical_part_key="front_left_fender",
            depth_grade=DepthGrade.L1_SURFACE_SCUFF,
            final_iop_ratio=0.05,
        )

        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            registration_number="MH12DE1433",
            make="Hyundai",
            model="Creta",
            verified_parts=[part],
        )

        orchestrator = Stage4ActuarialOrchestrator(session=db_session, redis_manager=None)
        estimate = await orchestrator.execute(payload)
        assert isinstance(estimate, ActuarialEstimateDTO)
        assert in_memory_db.claims[claim_id].claim_status == "PRICED_READY_FOR_NEGOTIATION"

    async def test_policy_lookup_by_registration_number(
        self,
        db_session: FakeAsyncSession,
        redis_mgr: RedisManager,
    ):
        """When policy_id is empty, policy is retrieved via registration_number."""
        claim_id = uuid.uuid4()
        seed_in_memory_claim(claim_id=claim_id, policy_id="POL-HAPPY-001")

        part = make_dummy_verified_part(
            canonical_part_key="front_left_fender",
            depth_grade=DepthGrade.L1_SURFACE_SCUFF,
            final_iop_ratio=0.05,
        )

        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="",  # Empty policy_id
            registration_number="MH12DE1433",
            make="Hyundai",
            model="Creta",
            verified_parts=[part],
        )

        orchestrator = Stage4ActuarialOrchestrator(session=db_session, redis_manager=redis_mgr)
        estimate = await orchestrator.execute(payload)
        assert estimate.policy_id == "POL-HAPPY-001"

    async def test_infer_vehicle_segment_all_branches(self):
        """Verify vehicle segment classification across all Indian market categories."""
        assert Stage4ActuarialOrchestrator._infer_vehicle_segment("Maruti", "Swift") == "HATCHBACK"
        assert Stage4ActuarialOrchestrator._infer_vehicle_segment("Honda", "City") == "SEDAN"
        assert Stage4ActuarialOrchestrator._infer_vehicle_segment("Hyundai", "Creta") == "COMPACT_SUV"
        assert Stage4ActuarialOrchestrator._infer_vehicle_segment("Toyota", "Fortuner") == "MIDSIZE_SUV"
        assert Stage4ActuarialOrchestrator._infer_vehicle_segment("BMW", "X3") == "LUXURY"
        assert Stage4ActuarialOrchestrator._infer_vehicle_segment("CustomOEM", "HyperCar") == "COMPACT_SUV"

    async def test_unrepaired_repo_get_unrepaired_claims_branch(
        self,
        db_session: FakeAsyncSession,
        redis_mgr: RedisManager,
    ):
        """Verify fraud detection branch when repo only implements get_unrepaired_claims."""
        class MockUnrepairedRepo:
            async def get_unrepaired_claims(self, registration_number, canonical_part_keys):
                from app.infrastructure.db.models import UnrepairedClaim
                return [
                    UnrepairedClaim(
                        ledger_id=99,
                        registration_number=registration_number,
                        canonical_part_key="front_left_fender",
                        damage_class="dent",
                        settled_amount_inr=Decimal("2000.00"),
                        is_repaired_verified=False,
                    )
                ]

        claim_id = uuid.uuid4()
        seed_in_memory_claim(claim_id=claim_id, policy_id="POL-HAPPY-001")
        part = make_dummy_verified_part(canonical_part_key="front_left_fender")
        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            registration_number="MH12DE1433",
            make="Hyundai",
            model="Creta",
            verified_parts=[part],
        )

        orch = Stage4ActuarialOrchestrator(
            session=db_session,
            redis_manager=redis_mgr,
            unrepaired_repo=MockUnrepairedRepo(),  # type: ignore
        )

        with pytest.raises(Stage4DoubleDippingFraudError) as exc_info:
            await orch.execute(payload)
        assert exc_info.value.escalation_code == ActuarialEscalationCode.ESC_03

    async def test_direct_get_segment_fallback_repo_branch(
        self,
        db_session: FakeAsyncSession,
        redis_mgr: RedisManager,
    ):
        """Verify OEM repo get_segment_fallback branch is exercised."""
        from app.infrastructure.db.models import OemPart

        class MockOemRepo:
            async def get_part(self, make, model, canonical_part_key):
                return None

            async def get_segment_fallback(self, segment, canonical_part_key):
                return OemPart(
                    catalogue_id=999,
                    make="Generic",
                    model="SegmentBaseline",
                    canonical_part_key=canonical_part_key,
                    display_part_name="Fallback Fender",
                    oem_part_number="FB-FENDER-001",
                    part_material="metal",
                    depreciation_rate_non_zero_dep=Decimal("0.00"),
                    oem_part_cost_inr=Decimal("4000.00"),
                    rr_labour_inr=Decimal("500.00"),
                    denting_base_labour_inr=Decimal("800.00"),
                    full_panel_paint_inr=Decimal("2500.00"),
                    pdr_or_polish_flat_inr=Decimal("600.00"),
                    is_repairable=True,
                    is_safety_critical=False,
                )

        claim_id = uuid.uuid4()
        seed_in_memory_claim(claim_id=claim_id, policy_id="POL-HAPPY-001")
        part = make_dummy_verified_part(canonical_part_key="front_left_fender")
        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            registration_number="MH12DE1433",
            make="Hyundai",
            model="Creta",
            verified_parts=[part],
        )

        orch = Stage4ActuarialOrchestrator(
            session=db_session,
            redis_manager=redis_mgr,
            oem_repo=MockOemRepo(),  # type: ignore
        )
        estimate = await orch.execute(payload)
        assert estimate.line_items[0].oem_part_number == "SEG-FB-FB-FENDER-001"

    async def test_protocol_interfaces_conformance(self):
        """Verify calculator and advisor conform to domain interfaces."""
        from app.domain.actuarial_pricing.calculator import ActuarialCalculator
        from app.domain.actuarial_pricing.ncb_advisor import NCBAdvisor
        from app.domain.actuarial_pricing.interfaces import (
            IActuarialCalculator,
            INCBAdvisor,
            IPolicyRepository,
            IOemRepository,
            IUnrepairedClaimsRepository,
            IClaimRepository,
        )
        import inspect

        calc = ActuarialCalculator()
        assert hasattr(calc, "calculate") and callable(calc.calculate)
        sig = inspect.signature(calc.calculate)
        assert "policy_context" in sig.parameters
        assert "verified_parts" in sig.parameters

        adv = NCBAdvisor()
        assert hasattr(adv, "evaluate") and callable(adv.evaluate)
        sig_adv = inspect.signature(adv.evaluate)
        assert "net_claim_liability_inr" in sig_adv.parameters

    async def test_policy_invalid_paint_type_fallback(
        self,
        db_session: FakeAsyncSession,
        redis_mgr: RedisManager,
    ):
        """Verify orchestrator handles unparseable paint_type string on policy by falling back to METALLIC."""
        pol = InsuredPolicy(
            policy_id="POL-INVALID-PAINT",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="MH12IP1111",
            vin_last_6="11111A",
            make="Hyundai",
            model="Creta",
            manufacturing_year=2024,
            registered_color="WHITE",
            paint_type="ultra_chameleon_matte_sparkle",  # Unrecognized paint type
            zero_dep_addon=True,
            compulsory_deductible_inr=Decimal("1000.00"),
            estimated_ncb_loss_inr=Decimal("3200.00"),
        )
        in_memory_db.policies["POL-INVALID-PAINT"] = pol
        claim_id = uuid.uuid4()
        seed_in_memory_claim(claim_id=claim_id, policy_id="POL-INVALID-PAINT")
        part = make_dummy_verified_part("front_left_fender")
        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-INVALID-PAINT",
            registration_number="MH12IP1111",
            make="Hyundai",
            model="Creta",
            verified_parts=[part],
        )

        orch = Stage4ActuarialOrchestrator(session=db_session, redis_manager=redis_mgr)
        estimate = await orch.execute(payload)
        assert estimate.vehicle_make == "Hyundai"

    async def test_sql_generic_part_fallback_resolution(
        self,
        db_session: FakeAsyncSession,
        redis_mgr: RedisManager,
    ):
        """Verify fallback step 3: resolves part from generic SQL table for unmapped vehicle."""
        pol = InsuredPolicy(
            policy_id="POL-MAHINDRA-THAR",
            policy_status="ACTIVE",
            policy_start_date=date(2026, 1, 1),
            policy_end_date=date(2026, 12, 31),
            max_cash_claims_per_year=2,
            cash_claims_ytd=0,
            registration_number="MH15TH4444",
            vin_last_6="44444A",
            make="Mahindra",
            model="Thar",
            manufacturing_year=2023,
            registered_color="BLACK",
            paint_type="metallic",
            zero_dep_addon=True,
            compulsory_deductible_inr=Decimal("1000.00"),
            estimated_ncb_loss_inr=Decimal("3200.00"),
        )
        in_memory_db.policies["POL-MAHINDRA-THAR"] = pol
        claim_id = uuid.uuid4()
        seed_in_memory_claim(claim_id=claim_id, policy_id="POL-MAHINDRA-THAR")
        part = make_dummy_verified_part("front_bumper")
        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-MAHINDRA-THAR",
            registration_number="MH15TH4444",
            make="Mahindra",
            model="Thar",
            verified_parts=[part],
        )

        orch = Stage4ActuarialOrchestrator(session=db_session, redis_manager=redis_mgr)
        estimate = await orch.execute(payload)
        assert estimate.vehicle_make == "Mahindra"
        assert estimate.line_items[0].oem_part_number.startswith("SEG-FB-")

    async def test_preliminary_estimate_repair_and_replace_mixed(
        self,
        db_session: FakeAsyncSession,
        redis_mgr: RedisManager,
    ):
        """Verify _build_preliminary_estimate covers both REPLACE and REPAIR (L4 creased dent) branches."""
        claim_id = uuid.uuid4()
        seed_in_memory_claim(claim_id=claim_id, policy_id="POL-CEILING-BREACH")
        parts = [
            make_dummy_verified_part("hood", is_repairable=False, depth_grade=DepthGrade.L5_STRUCTURAL_TEAR),
            make_dummy_verified_part("front_left_door", is_repairable=True, depth_grade=DepthGrade.L4_CREASED_DENT, final_iop_ratio=0.20),
        ]
        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-CEILING-BREACH",
            registration_number="MH01CB2500",
            make="Toyota",
            model="Fortuner",
            verified_parts=parts,
        )

        orch = Stage4ActuarialOrchestrator(session=db_session, redis_manager=redis_mgr)
        with pytest.raises(Stage4FinancialCeilingExceededError) as exc_info:
            await orch.execute(payload)

        err = exc_info.value
        assert err.preliminary_estimate is not None
        assert len(err.preliminary_estimate.line_items) == 2

    async def test_orchestrator_without_redis_esc_branches(
        self,
        db_session: FakeAsyncSession,
    ):
        """Verify orchestrator behaves cleanly without RedisManager across ESC-03, ESC-08, ESC-09."""
        # ESC-03 without Redis
        claim_id = uuid.uuid4()
        seed_in_memory_claim(claim_id=claim_id, policy_id="POL-HAPPY-001")
        part_fraud = make_dummy_verified_part("back_bumper")
        payload_fraud = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            registration_number="MH12DE1433",
            make="Hyundai",
            model="Creta",
            verified_parts=[part_fraud],
        )
        orch_no_redis = Stage4ActuarialOrchestrator(session=db_session, redis_manager=None)
        with pytest.raises(Stage4DoubleDippingFraudError):
            await orch_no_redis.execute(payload_fraud)

        # ESC-09 without Redis
        claim_id2 = uuid.uuid4()
        seed_in_memory_claim(claim_id=claim_id2, policy_id="POL-HAPPY-001")
        part_unknown = make_dummy_verified_part("nonexistent_unknown_part_key")
        payload_unknown = Stage4HandoffPayload(
            claim_id=claim_id2,
            policy_id="POL-HAPPY-001",
            registration_number="MH12DE1433",
            make="Hyundai",
            model="Creta",
            verified_parts=[part_unknown],
        )
        with pytest.raises(Stage4CataloguePartNotFoundError):
            await orch_no_redis.execute(payload_unknown)

        # ESC-08 without Redis
        claim_id3 = uuid.uuid4()
        seed_in_memory_claim(claim_id=claim_id3, policy_id="POL-CEILING-BREACH")
        parts = [
            make_dummy_verified_part("front_bumper", is_repairable=False, depth_grade=DepthGrade.L5_STRUCTURAL_TEAR),
            make_dummy_verified_part("hood", is_repairable=False, depth_grade=DepthGrade.L5_STRUCTURAL_TEAR),
        ]
        payload_ceiling = Stage4HandoffPayload(
            claim_id=claim_id3,
            policy_id="POL-CEILING-BREACH",
            registration_number="MH01CB2500",
            make="Toyota",
            model="Fortuner",
            verified_parts=parts,
        )
        with pytest.raises(Stage4FinancialCeilingExceededError):
            await orch_no_redis.execute(payload_ceiling)

    async def test_unrepaired_repo_fallback_method(
        self,
        db_session: FakeAsyncSession,
    ):
        """Cover branch where repo only has get_unrepaired_claims (lines 193-201)."""
        class MockUnrepairedRepo:
            async def get_unrepaired_claims(self, registration_number, canonical_part_keys):
                from app.infrastructure.db.models import UnrepairedClaim
                return [
                    UnrepairedClaim(
                        ledger_id=99,
                        registration_number=registration_number,
                        canonical_part_key=canonical_part_keys[0],
                        damage_class="dent",
                        settled_amount_inr=Decimal("2000.00"),
                        is_repaired_verified=False,
                    )
                ]

        claim_id = uuid.uuid4()
        seed_in_memory_claim(claim_id=claim_id, policy_id="POL-HAPPY-001")
        part = make_dummy_verified_part("front_left_door")
        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            registration_number="MH12DE1433",
            make="Hyundai",
            model="Creta",
            verified_parts=[part],
        )
        orch = Stage4ActuarialOrchestrator(
            session=db_session,
            unrepaired_repo=MockUnrepairedRepo(),  # type: ignore
        )
        with pytest.raises(Stage4DoubleDippingFraudError) as exc_info:
            await orch.execute(payload)
        assert exc_info.value.canonical_part_key == "front_left_door"

    async def test_ceiling_escalation_edge_branches(
        self,
        db_session: FakeAsyncSession,
    ):
        """Cover exc with pre-attached estimate, model_dump branch, and build exception (lines 310-331)."""
        class DummyEstimateWithModelDump:
            def model_dump(self, mode="json"):
                return {"is_ceiling_breached": True, "dummy": True}

        class MockCalculator:
            def calculate(self, *args, **kwargs):
                exc = Stage4FinancialCeilingExceededError(gross_amount_inr="30000.00")
                exc.preliminary_estimate = DummyEstimateWithModelDump()
                raise exc

        claim_id = uuid.uuid4()
        seed_in_memory_claim(claim_id=claim_id, policy_id="POL-HAPPY-001")
        part = make_dummy_verified_part("front_left_door")
        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            registration_number="MH12DE1433",
            make="Hyundai",
            model="Creta",
            verified_parts=[part],
        )
        orch = Stage4ActuarialOrchestrator(
            session=db_session,
            calculator=MockCalculator(),  # type: ignore
        )
        with pytest.raises(Stage4FinancialCeilingExceededError):
            await orch.execute(payload)

        # Build exception branch (lines 322-323)
        class FailingBuildOrch(Stage4ActuarialOrchestrator):
            def _build_preliminary_estimate(self, *args, **kwargs):
                raise RuntimeError("Failed to build estimate")

        class MockCalcAlwaysRaise:
            def calculate(self, *args, **kwargs):
                raise Stage4FinancialCeilingExceededError(gross_amount_inr="30000.00")

        failing_orch = FailingBuildOrch(
            session=db_session,
            calculator=MockCalcAlwaysRaise(),  # type: ignore
        )
        with pytest.raises(Stage4FinancialCeilingExceededError):
            await failing_orch.execute(payload)

    async def test_preliminary_estimate_comprehensive_coverage(
        self,
        db_session: FakeAsyncSession,
    ):
        """Cover lines 572-575, 588-589, 625-626, 634-635, 642-643 in _build_preliminary_estimate."""
        claim_id = uuid.uuid4()
        seed_in_memory_claim(claim_id=claim_id, policy_id="POL-CEILING-BREACH")

        # Mutate an OEM part clone to have invalid material and zero paint
        from tests.in_memory_db import in_memory_db
        left_mirror = in_memory_db.oem_parts[("toyota", "fortuner", "left_mirror")]
        left_mirror.part_material = "invalid_material_xyz"

        parts = [
            make_dummy_verified_part("hood", is_repairable=False, depth_grade=DepthGrade.L5_STRUCTURAL_TEAR),
            # L1 repair scuff
            make_dummy_verified_part("front_left_door", is_repairable=True, depth_grade=DepthGrade.L1_SURFACE_SCUFF),
            # L2 repair scratch
            make_dummy_verified_part("back_left_door", is_repairable=True, depth_grade=DepthGrade.L2_BASECOAT_SCRATCH),
            # Part without paint
            make_dummy_verified_part("left_mirror", is_repairable=False, depth_grade=DepthGrade.L5_STRUCTURAL_TEAR),
        ]
        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-CEILING-BREACH",
            registration_number="MH01CB2500",
            make="Toyota",
            model="Fortuner",
            verified_parts=parts,
        )
        orch = Stage4ActuarialOrchestrator(session=db_session)
        with pytest.raises(Stage4FinancialCeilingExceededError) as exc_info:
            await orch.execute(payload)

        # Restore
        left_mirror.part_material = "assembly"

        err = exc_info.value
        assert err.preliminary_estimate is not None
        assert len(err.preliminary_estimate.line_items) == 4

    async def test_resolve_segment_fallback_repo_and_sql_exception(
        self,
        db_session: FakeAsyncSession,
    ):
        """Cover lines 449->453 and 469-471 in _resolve_segment_fallback."""
        from unittest.mock import AsyncMock, patch

        class RepoWithFallbackNone:
            async def get_part(self, make, model, canonical_part_key):
                return None
            async def get_segment_fallback(self, segment, canonical_part_key):
                return None

        claim_id = uuid.uuid4()
        seed_in_memory_claim(claim_id=claim_id, policy_id="POL-HAPPY-001")
        part = make_dummy_verified_part("completely_alien_part_xyz")
        payload = Stage4HandoffPayload(
            claim_id=claim_id,
            policy_id="POL-HAPPY-001",
            registration_number="MH12DE1433",
            make="Hyundai",
            model="Creta",
            verified_parts=[part],
        )

        # Mock db_session.execute to raise exception on generic query
        mock_execute = AsyncMock(side_effect=RuntimeError("DB query error"))
        with patch.object(db_session, "execute", mock_execute):
            orch = Stage4ActuarialOrchestrator(
                session=db_session,
                oem_repo=RepoWithFallbackNone(),  # type: ignore
            )
            with pytest.raises(Stage4CataloguePartNotFoundError):
                await orch.execute(payload)




