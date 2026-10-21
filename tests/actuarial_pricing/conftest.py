"""
tests/actuarial_pricing/conftest.py
Hermetic test fixtures and in-memory DB configuration for Stage 4 tests.
"""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
import pytest
import pytest_asyncio

from app.domain.actuarial_pricing.enums import MaterialType, PaintType, RepairAction
from app.domain.actuarial_pricing.schemas import PolicyPricingContextDTO
from app.domain.vlm_damage_inspection.schemas import (
    DepthGrade,
    Stage4HandoffPayload,
    VerifiedDamagedPart,
)
from app.infrastructure.cache.redis_manager import RedisManager
from app.infrastructure.db.models import Claim
from tests.in_memory_db import (
    FakeAsyncSession,
    in_memory_db,
    patch_in_memory_db,
)

# Apply hermetic in-memory patches for repositories and RedisManager
patch_in_memory_db()


@pytest.fixture(autouse=True)
def reset_in_memory_state():
    """Guarantee pristine state for each test execution."""
    in_memory_db.reset()


@pytest.fixture
def db_session() -> FakeAsyncSession:
    """Yield a hermetic FakeAsyncSession resolving against in_memory_db."""
    return FakeAsyncSession()


@pytest.fixture
def redis_mgr() -> RedisManager:
    """Provide RedisManager backed by hermetic in_memory_db event store."""
    return RedisManager()


@pytest.fixture
def calculator() -> "ActuarialCalculator":
    """Provide ActuarialCalculator instance."""
    from app.domain.actuarial_pricing.calculator import ActuarialCalculator
    return ActuarialCalculator()



def make_dummy_verified_part(
    canonical_part_key: str = "front_left_door",
    depth_grade: DepthGrade | str = DepthGrade.L4_CREASED_DENT,
    final_iop_ratio: float = 0.15,
    is_repairable: bool = True,
    is_safety_critical: bool = False,
    part_material: str = "metal",
    display_part_name: Optional[str] = None,
) -> VerifiedDamagedPart:
    """Construct a VerifiedDamagedPart for tests."""
    dg = (
        depth_grade
        if isinstance(depth_grade, DepthGrade)
        else DepthGrade(depth_grade)
    )
    return VerifiedDamagedPart(
        canonical_part_key=canonical_part_key,
        raw_detected_part_classes=[canonical_part_key],
        side_resolution_method="heuristic",
        display_part_name=display_part_name or canonical_part_key.replace("_", " ").title(),
        oem_part_number=f"OEM-{canonical_part_key.upper()}-001",
        part_material=part_material,
        is_repairable=is_repairable,
        is_safety_critical=is_safety_critical,
        detected_damage_classes=["dent"],
        primary_damage_class="dent",
        final_iop_ratio=final_iop_ratio,
        iop_percentage=round(final_iop_ratio * 100.0, 2),
        iop_estimation_method="mask_ratio",
        zoom_clipped_frames_filtered=0,
        persistence_frame_count=10,
        part_confidence=0.95,
        damage_confidence=0.92,
        area_measurement_keyframe="frame_001.jpg",
        vlm_closeup_keyframe="frame_002.jpg",
        som_annotated_crop_path=Path("/tmp/som_crop.jpg"),
        som_raw_crop_path=Path("/tmp/som_raw.jpg"),
        depth_grade=dg,
        vlm_confidence=0.91,
        visual_reasoning_short="Visible deformation on outer panel without structural shearing.",
    )


def make_policy_context(
    policy_id: str = "POL-HAPPY-001",
    registration_number: str = "MH12DE1433",
    make: str = "Hyundai",
    model: str = "Creta",
    manufacturing_year: int = 2023,
    zero_dep_addon: bool = True,
    paint_type: PaintType | str = PaintType.METALLIC,
    compulsory_deductible_inr: Decimal = Decimal("1000.00"),
    voluntary_deductible_inr: Decimal = Decimal("0.00"),
    estimated_ncb_loss_inr: Decimal = Decimal("3200.00"),
    engine_cc: Optional[int] = 1497,
) -> PolicyPricingContextDTO:
    """Construct a PolicyPricingContextDTO for testing calculator and rules."""
    if isinstance(paint_type, str):
        try:
            pt = PaintType(paint_type.lower())
        except ValueError:
            pt = paint_type  # type: ignore
    else:
        pt = paint_type
    return PolicyPricingContextDTO(
        policy_id=policy_id,
        registration_number=registration_number,
        make=make,
        model=model,
        manufacturing_year=manufacturing_year,
        zero_dep_addon=zero_dep_addon,
        paint_type=pt,
        compulsory_deductible_inr=compulsory_deductible_inr,
        voluntary_deductible_inr=voluntary_deductible_inr,
        estimated_ncb_loss_inr=estimated_ncb_loss_inr,
        engine_cc=engine_cc,
    )


def seed_in_memory_claim(
    claim_id: Optional[uuid.UUID] = None,
    policy_id: str = "POL-HAPPY-001",
    current_stage: str = "STAGE_3_VLM_INSPECTION",
    claim_status: str = "PROCESSING",
) -> Claim:
    """Create and insert a Claim record into in_memory_db."""
    cid = claim_id or uuid.uuid4()
    claim = Claim(
        claim_id=cid,
        policy_id=policy_id,
        video_sha256="aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899",
        capture_source="mobile_sdk",
        current_stage=current_stage,
        claim_status=claim_status,
        actuarial_estimate=None,
    )
    in_memory_db.claims[cid] = claim
    return claim
