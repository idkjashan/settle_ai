"""
tests/in_memory_db.py
Hermetic In-Memory Database & Redis mock for Stage 0, Stage 1 & Stage 2 isolated test execution.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from app.infrastructure.db.models import Claim, InsuredPolicy, OemPart, UnrepairedClaim
import app.infrastructure.db.repositories as repos
import app.infrastructure.cache.redis_manager as rm

HYUNDAI_CRETA_PARTS = [
    ("front_bumper", "Front Bumper Cover", "86511-M0000", "plastic", Decimal("8800.00"), Decimal("850.00"), Decimal("1100.00"), Decimal("3800.00"), Decimal("800.00"), True, False),
    ("back_bumper", "Rear Bumper Cover", "86611-M0000", "plastic", Decimal("8200.00"), Decimal("850.00"), Decimal("1100.00"), Decimal("3600.00"), Decimal("800.00"), True, False),
    ("hood", "Front Bonnet / Hood Panel", "66400-M0000", "metal", Decimal("14200.00"), Decimal("1100.00"), Decimal("1600.00"), Decimal("4800.00"), Decimal("950.00"), True, False),
    ("trunk", "Rear Trunk Lid Panel", "69200-M0000", "metal", Decimal("13500.00"), Decimal("1150.00"), Decimal("1500.00"), Decimal("4400.00"), Decimal("900.00"), True, False),
    ("tailgate", "Rear Tailgate Assembly", "73700-M0000", "metal", Decimal("15800.00"), Decimal("1250.00"), Decimal("1600.00"), Decimal("4500.00"), Decimal("900.00"), True, False),
    ("front_left_door", "Front Left Door Panel", "76003-M0000", "metal", Decimal("11500.00"), Decimal("950.00"), Decimal("1400.00"), Decimal("4200.00"), Decimal("850.00"), True, False),
    ("front_right_door", "Front Right Door Panel", "76004-M0000", "metal", Decimal("11500.00"), Decimal("950.00"), Decimal("1400.00"), Decimal("4200.00"), Decimal("850.00"), True, False),
    ("front_door", "Front Door Panel (Generic Alias)", "76003-M0000", "metal", Decimal("11500.00"), Decimal("950.00"), Decimal("1400.00"), Decimal("4200.00"), Decimal("850.00"), True, False),
    ("back_left_door", "Rear Left Door Panel", "77003-M0000", "metal", Decimal("10800.00"), Decimal("900.00"), Decimal("1350.00"), Decimal("4000.00"), Decimal("850.00"), True, False),
    ("back_right_door", "Rear Right Door Panel", "77004-M0000", "metal", Decimal("10800.00"), Decimal("900.00"), Decimal("1350.00"), Decimal("4000.00"), Decimal("850.00"), True, False),
    ("back_door", "Rear Door Panel (Generic Alias)", "77003-M0000", "metal", Decimal("10800.00"), Decimal("900.00"), Decimal("1350.00"), Decimal("4000.00"), Decimal("850.00"), True, False),
    ("left_mirror", "Left Outside Rear View Mirror", "87610-M0000", "assembly", Decimal("6400.00"), Decimal("450.00"), Decimal("0.00"), Decimal("900.00"), Decimal("400.00"), False, False),
    ("right_mirror", "Right Outside Rear View Mirror", "87620-M0000", "assembly", Decimal("6400.00"), Decimal("450.00"), Decimal("0.00"), Decimal("900.00"), Decimal("400.00"), False, False),
    ("front_left_light", "Front Left LED Headlamp", "92101-M0000", "assembly", Decimal("16500.00"), Decimal("650.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, False),
    ("front_right_light", "Front Right LED Headlamp", "92102-M0000", "assembly", Decimal("16500.00"), Decimal("650.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, False),
    ("front_light", "Front LED Headlamp Assembly (Generic Alias)", "92101-M0000", "assembly", Decimal("16500.00"), Decimal("650.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, False),
    ("back_left_light", "Rear Left Tail Lamp Assembly", "92401-M0000", "assembly", Decimal("7200.00"), Decimal("500.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, False),
    ("back_right_light", "Rear Right Tail Lamp Assembly", "92402-M0000", "assembly", Decimal("7200.00"), Decimal("500.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, False),
    ("back_light", "Rear Tail Lamp Assembly (Generic Alias)", "92401-M0000", "assembly", Decimal("7200.00"), Decimal("500.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, False),
    ("front_glass", "Front Laminated Windshield", "86110-M0000", "glass", Decimal("12400.00"), Decimal("1800.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, True),
    ("back_glass", "Rear Heated Windshield Glass", "87110-M0000", "glass", Decimal("9200.00"), Decimal("1500.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, True),
    ("wheel", "Alloy Wheel & Tire Assembly", "52910-M0000", "assembly", Decimal("18500.00"), Decimal("600.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), False, True),
]


class InMemoryDatabase:
    """Hermetic in-memory store for policies, claims, OEM parts, unrepaired claims, and Redis locks."""
    def __init__(self):
        self.claims: Dict[uuid.UUID, Claim] = {}
        self.locks: Dict[str, str] = {}
        self.events: List[Dict[str, Any]] = []
        self.policies: Dict[str, InsuredPolicy] = self._seed_policies()
        self.oem_parts: Dict[Tuple[str, str, str], OemPart] = self._seed_oem_parts()
        self.unrepaired_claims: List[UnrepairedClaim] = self._seed_unrepaired()

    def reset(self):
        self.claims.clear()
        self.locks.clear()
        self.events.clear()
        self.policies = self._seed_policies()
        self.oem_parts = self._seed_oem_parts()
        self.unrepaired_claims = self._seed_unrepaired()

    def _seed_policies(self) -> Dict[str, InsuredPolicy]:
        return {
            "POL-HAPPY-001": InsuredPolicy(
                policy_id="POL-HAPPY-001",
                policy_status="ACTIVE",
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=0,
                registration_number="MH12DE1433",
                vin_last_6="89412B",
                make="Hyundai",
                model="Creta",
                manufacturing_year=2023,
                registered_color="WHITE",
                registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 45, "v_min": 180, "v_max": 255},
                paint_type="metallic",
                zero_dep_addon=True,
                compulsory_deductible_inr=Decimal("1000.00"),
                estimated_ncb_loss_inr=Decimal("3200.00"),
            ),
            "POL-EXPIRED-002": InsuredPolicy(
                policy_id="POL-EXPIRED-002",
                policy_status="ACTIVE",
                policy_start_date=date(2024, 1, 1),
                policy_end_date=date(2024, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=0,
                registration_number="DL01AB9999",
                vin_last_6="12345A",
                make="Maruti",
                model="Swift",
                manufacturing_year=2021,
                registered_color="SILVER",
                registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 50, "v_min": 100, "v_max": 220},
                paint_type="metallic",
                zero_dep_addon=False,
                compulsory_deductible_inr=Decimal("1500.00"),
                estimated_ncb_loss_inr=Decimal("2500.00"),
            ),
            "POL-CLAIMCAP-004": InsuredPolicy(
                policy_id="POL-CLAIMCAP-004",
                policy_status="ACTIVE",
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=2,
                registration_number="MH14EU4321",
                vin_last_6="55443D",
                make="Tata",
                model="Nexon",
                manufacturing_year=2022,
                registered_color="BLUE",
                registered_color_hsv={"h_min": 100, "h_max": 130, "s_min": 80, "s_max": 255, "v_min": 50, "v_max": 255},
                paint_type="metallic",
                zero_dep_addon=True,
                compulsory_deductible_inr=Decimal("1000.00"),
                estimated_ncb_loss_inr=Decimal("2800.00"),
            ),
            "POL-CANCELLED-005": InsuredPolicy(
                policy_id="POL-CANCELLED-005",
                policy_status="CANCELLED",
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=0,
                registration_number="MH02BQ1111",
                vin_last_6="99887E",
                make="Honda",
                model="City",
                manufacturing_year=2020,
                registered_color="WHITE",
                registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 45, "v_min": 180, "v_max": 255},
                paint_type="solid",
                zero_dep_addon=False,
                compulsory_deductible_inr=Decimal("2000.00"),
                estimated_ncb_loss_inr=Decimal("4000.00"),
            ),
            "POL-RED-007": InsuredPolicy(
                policy_id="POL-RED-007",
                policy_status="ACTIVE",
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=0,
                registration_number="KA01MJ5555",
                vin_last_6="33221F",
                make="Hyundai",
                model="Creta",
                manufacturing_year=2023,
                registered_color="RED",
                registered_color_hsv={"h_min": 0, "h_max": 10, "s_min": 100, "s_max": 255, "v_min": 80, "v_max": 255},
                paint_type="metallic",
                zero_dep_addon=True,
                compulsory_deductible_inr=Decimal("1000.00"),
                estimated_ncb_loss_inr=Decimal("3200.00"),
            ),
        }

    def _seed_oem_parts(self) -> Dict[Tuple[str, str, str], OemPart]:
        parts = {}
        # Hyundai Creta
        for idx, (key, name, pnum, mat, cost, rr, dent, paint, pdr, rep, safe) in enumerate(HYUNDAI_CRETA_PARTS, start=1):
            part = OemPart(
                catalogue_id=idx,
                make="Hyundai",
                model="Creta",
                canonical_part_key=key,
                display_part_name=name,
                oem_part_number=pnum,
                part_material=mat,
                depreciation_rate_non_zero_dep=Decimal("0.00"),
                oem_part_cost_inr=cost,
                rr_labour_inr=rr,
                denting_base_labour_inr=dent,
                full_panel_paint_inr=paint,
                pdr_or_polish_flat_inr=pdr,
                is_repairable=rep,
                is_safety_critical=safe,
            )
            parts[("hyundai", "creta", key)] = part

        # Maruti Swift (0.72x)
        m_swift = Decimal("0.72")
        for idx, (key, name, pnum, mat, cost, rr, dent, paint, pdr, rep, safe) in enumerate(HYUNDAI_CRETA_PARTS, start=100):
            part = OemPart(
                catalogue_id=idx,
                make="Maruti",
                model="Swift",
                canonical_part_key=key,
                display_part_name=name,
                oem_part_number=f"71811-{key[:4].upper()}",
                part_material=mat,
                depreciation_rate_non_zero_dep=Decimal("0.00"),
                oem_part_cost_inr=(cost * m_swift).quantize(Decimal("0.01")),
                rr_labour_inr=(rr * m_swift).quantize(Decimal("0.01")),
                denting_base_labour_inr=(dent * m_swift).quantize(Decimal("0.01")),
                full_panel_paint_inr=(paint * m_swift).quantize(Decimal("0.01")),
                pdr_or_polish_flat_inr=(pdr * m_swift).quantize(Decimal("0.01")),
                is_repairable=rep,
                is_safety_critical=safe,
            )
            parts[("maruti", "swift", key)] = part

        # Tata Nexon (0.85x)
        m_nexon = Decimal("0.85")
        for idx, (key, name, pnum, mat, cost, rr, dent, paint, pdr, rep, safe) in enumerate(HYUNDAI_CRETA_PARTS, start=200):
            part = OemPart(
                catalogue_id=idx,
                make="Tata",
                model="Nexon",
                canonical_part_key=key,
                display_part_name=name,
                oem_part_number=f"5424-{key[:4].upper()}",
                part_material=mat,
                depreciation_rate_non_zero_dep=Decimal("0.00"),
                oem_part_cost_inr=(cost * m_nexon).quantize(Decimal("0.01")),
                rr_labour_inr=(rr * m_nexon).quantize(Decimal("0.01")),
                denting_base_labour_inr=(dent * m_nexon).quantize(Decimal("0.01")),
                full_panel_paint_inr=(paint * m_nexon).quantize(Decimal("0.01")),
                pdr_or_polish_flat_inr=(pdr * m_nexon).quantize(Decimal("0.01")),
                is_repairable=rep,
                is_safety_critical=safe,
            )
            parts[("tata", "nexon", key)] = part

        return parts

    def _seed_unrepaired(self) -> List[UnrepairedClaim]:
        return [
            UnrepairedClaim(
                ledger_id=1,
                registration_number="MH12DE1433",
                canonical_part_key="back_bumper",
                damage_class="dent",
                settled_amount_inr=Decimal("4200.00"),
                is_repaired_verified=False,
                settled_at=datetime(2026, 9, 15),
            )
        ]


in_memory_db = InMemoryDatabase()


class FakeResult:
    def __init__(self, items: list):
        self._items = items

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None

    def scalars(self):
        return self

    def first(self):
        return self._items[0] if self._items else None

    def all(self):
        return list(self._items)


class FakeAsyncSession:
    """AsyncSession mock that intercepts SQLAlchemy queries and resolves against in_memory_db."""
    async def execute(self, stmt):
        stmt_str = str(stmt).lower()
        # 1. InsuredPolicy query
        if "from insured_policies" in stmt_str or "insured_policies." in stmt_str:
            # Check for policy_id
            for pol_id, policy in in_memory_db.policies.items():
                if pol_id.lower() in stmt_str or f"'{pol_id.lower()}'" in stmt_str:
                    return FakeResult([policy])
            # If where clause was compiled with bound params, inspect params if available
            try:
                params = stmt.compile().params
                for k, v in params.items():
                    if isinstance(v, str) and v in in_memory_db.policies:
                        return FakeResult([in_memory_db.policies[v]])
            except Exception:
                pass
            return FakeResult(list(in_memory_db.policies.values()))

        # 2. UnrepairedClaimsLedger query
        if "from unrepaired_claims_ledger" in stmt_str or "unrepaired_claims_ledger." in stmt_str:
            try:
                params = stmt.compile().params
                reg = None
                keys = []
                for k, v in params.items():
                    if isinstance(v, str) and len(v) >= 8 and any(c.isdigit() for c in v):
                        reg = v
                    elif isinstance(v, (list, tuple)):
                        keys.extend(v)
                    elif isinstance(v, str) and "_" in v:
                        keys.append(v)
                matched = [
                    u for u in in_memory_db.unrepaired_claims
                    if (not reg or u.registration_number == reg)
                    and (not keys or u.canonical_part_key in keys)
                    and not u.is_repaired_verified
                ]
                return FakeResult(matched)
            except Exception:
                return FakeResult([u for u in in_memory_db.unrepaired_claims if not u.is_repaired_verified])

        # 3. OEMPartsCatalogue query
        if "from oem_parts_catalogue" in stmt_str or "oem_parts_catalogue." in stmt_str:
            try:
                params = stmt.compile().params
                make = None
                model = None
                part_keys = []
                for k, v in params.items():
                    if isinstance(v, str):
                        v_lower = v.lower()
                        if v_lower in ("hyundai", "maruti", "tata", "hoda", "kia"):
                            make = v_lower
                        elif v_lower in ("creta", "swift", "nexon", "city", "seltos"):
                            model = v_lower
                        elif any(p[0] == v_lower for p in HYUNDAI_CRETA_PARTS) or "_" in v:
                            part_keys.append(v_lower)
                    elif isinstance(v, (list, tuple)):
                        part_keys.extend([x.lower() if isinstance(x, str) else x for x in v])

                make = make or "hyundai"
                model = model or "creta"
                matched = []
                for (m, mdl, pkey), part in in_memory_db.oem_parts.items():
                    if m == make and mdl == model:
                        if not part_keys or pkey in part_keys:
                            matched.append(part)
                return FakeResult(matched)
            except Exception:
                return FakeResult(list(in_memory_db.oem_parts.values()))

        # 4. Claim update / select
        if "update claims" in stmt_str:
            try:
                params = stmt.compile().params
                cid = None
                for k, v in params.items():
                    if isinstance(v, uuid.UUID):
                        cid = v
                        break
                if cid and cid in in_memory_db.claims:
                    c = in_memory_db.claims[cid]
                    for k, v in params.items():
                        if hasattr(c, k):
                            setattr(c, k, v)
            except Exception:
                pass
            return FakeResult([])

        if "from claims" in stmt_str:
            return FakeResult(list(in_memory_db.claims.values()))

        return FakeResult([])

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def close(self):
        pass


async def fake_get_by_id(self, policy_id: str) -> Optional[InsuredPolicy]:
    return in_memory_db.policies.get(policy_id)


async def fake_get_by_registration(self, registration_number: str) -> Optional[InsuredPolicy]:
    return next((p for p in in_memory_db.policies.values() if p.registration_number == registration_number), None)


async def fake_claim_get_by_id(self, claim_id: uuid.UUID) -> Optional[Claim]:
    return in_memory_db.claims.get(claim_id)


async def fake_check_historical_duplicate(self, video_sha256: str) -> bool:
    for c in in_memory_db.claims.values():
        if (
            c.video_sha256 == video_sha256
            and c.claim_status not in ("REJECTED_FAST_FAIL", "REJECTED_STAGE0")
            and not c.is_demo_rehearsal
        ):
            return True
    return False


async def fake_create_claim(self, claim: Claim) -> Claim:
    in_memory_db.claims[claim.claim_id] = claim
    return claim


async def fake_update_claim_stage(
    self,
    claim_id: uuid.UUID,
    stage: str,
    status: str,
    escalation_code: Optional[str] = None,
    failure_codes: Optional[List[str]] = None,
    telemetry_update: Optional[Dict[str, Any]] = None,
    telemetry_column: Optional[str] = None,
) -> Optional[Claim]:
    claim = in_memory_db.claims.get(claim_id)
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
    return claim


async def fake_reset_demo_state(self) -> Dict[str, Any]:
    to_del = [
        cid for cid, c in in_memory_db.claims.items()
        if c.is_demo_rehearsal or (c.policy_id and c.policy_id.startswith("POL-HAPPY-"))
    ]
    for cid in to_del:
        del in_memory_db.claims[cid]

    if "POL-HAPPY-001" in in_memory_db.policies:
        in_memory_db.policies["POL-HAPPY-001"].cash_claims_ytd = 0

    return {"deleted_claims": len(to_del), "reset_policy": "POL-HAPPY-001"}


async def fake_get_part(self, make: str, model: str, canonical_part_key: str) -> Optional[OemPart]:
    return in_memory_db.oem_parts.get((make.lower(), model.lower(), canonical_part_key))


async def fake_has_unrepaired_claim(self, registration_number: str, canonical_part_key: str) -> bool:
    return any(
        u.registration_number == registration_number and u.canonical_part_key == canonical_part_key and not u.is_repaired_verified
        for u in in_memory_db.unrepaired_claims
    )


async def fake_acquire_video_lock(self, video_sha256: str, claim_id: uuid.UUID, ttl_sec: int = 60) -> bool:
    if video_sha256 in in_memory_db.locks:
        return False
    in_memory_db.locks[video_sha256] = str(claim_id)
    return True


async def fake_release_video_lock(self, video_sha256: str) -> bool:
    if video_sha256 in in_memory_db.locks:
        del in_memory_db.locks[video_sha256]
        return True
    return False


async def fake_publish_event(self, claim_id: uuid.UUID, event_name: str, payload: Dict[str, Any]) -> None:
    in_memory_db.events.append({"claim_id": claim_id, "event": event_name, "data": payload})


async def fake_flush_locks(self) -> int:
    count = len(in_memory_db.locks)
    in_memory_db.locks.clear()
    return count


async def fake_close(self) -> None:
    pass


def patch_in_memory_db():
    repos.PolicyRepository.get_by_id = fake_get_by_id
    repos.PolicyRepository.get_by_registration = fake_get_by_registration
    repos.ClaimRepository.get_by_id = fake_claim_get_by_id
    repos.ClaimRepository.check_historical_duplicate = fake_check_historical_duplicate
    repos.ClaimRepository.create_claim = fake_create_claim
    repos.ClaimRepository.update_claim_stage = fake_update_claim_stage
    repos.DemoResetRepository.reset_demo_state = fake_reset_demo_state
    repos.OemRepository.get_part = fake_get_part
    repos.UnrepairedClaimsRepository.has_unrepaired_claim = fake_has_unrepaired_claim

    rm.RedisManager.acquire_video_lock = fake_acquire_video_lock
    rm.RedisManager.release_video_lock = fake_release_video_lock
    rm.RedisManager.publish_event = fake_publish_event
    rm.RedisManager.flush_locks = fake_flush_locks
    rm.RedisManager.close = fake_close
