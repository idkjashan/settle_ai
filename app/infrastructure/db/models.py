import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Any
from sqlalchemy import (
    String, Boolean, SmallInteger, Integer, Numeric, Date, DateTime, Text, ForeignKey,
    Index, func
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class InsuredPolicy(Base):
    __tablename__ = "insured_policies"

    policy_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    policy_status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)
    policy_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    policy_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    max_cash_claims_per_year: Mapped[int] = mapped_column(SmallInteger, default=2, nullable=False)
    cash_claims_ytd: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    registration_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    vin_last_6: Mapped[str] = mapped_column(String(6), nullable=False)
    make: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    manufacturing_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    registered_color: Mapped[str] = mapped_column(String(30), nullable=False)
    registered_color_hsv: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    paint_type: Mapped[str] = mapped_column(String(20), default="metallic", nullable=False)
    zero_dep_addon: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    compulsory_deductible_inr: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("1000.00"), nullable=False)
    estimated_ncb_loss_inr: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("3200.00"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    claims: Mapped[List["Claim"]] = relationship("Claim", back_populates="policy")

class Claim(Base):
    __tablename__ = "claims"

    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[str] = mapped_column(String(32), ForeignKey("insured_policies.policy_id"), nullable=False)
    video_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    capture_source: Mapped[str] = mapped_column(String(20), nullable=False)
    is_demo_rehearsal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw_video_s3_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_stage: Mapped[str] = mapped_column(String(30), default="STAGE_0_SANITY", nullable=False)
    claim_status: Mapped[str] = mapped_column(String(30), default="PROCESSING", nullable=False)
    escalation_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    failure_codes: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text), nullable=True)
    fast_fail_telemetry: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    vehicle_continuity_telemetry: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    dual_mask_telemetry: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    vlm_inspection_telemetry: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    actuarial_estimate: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    policy: Mapped["InsuredPolicy"] = relationship("InsuredPolicy", back_populates="claims")

    __table_args__ = (
        Index(
            "idx_claims_unique_active_video_sha256",
            "video_sha256",
            unique=True,
            postgresql_where=(
                (claim_status.notin_(["REJECTED_FAST_FAIL", "REJECTED_STAGE0"])) &
                (is_demo_rehearsal == False)
            ),
        ),
    )

class OemPart(Base):
    __tablename__ = "oem_parts_catalogue"

    catalogue_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    make: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    canonical_part_key: Mapped[str] = mapped_column(String(50), nullable=False)
    display_part_name: Mapped[str] = mapped_column(String(100), nullable=False)
    oem_part_number: Mapped[str] = mapped_column(String(40), nullable=False)
    part_material: Mapped[str] = mapped_column(String(20), nullable=False)
    oem_part_cost_inr: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    rr_labour_inr: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    denting_base_labour_inr: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    full_panel_paint_inr: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    pdr_or_polish_flat_inr: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_repairable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_safety_critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("idx_oem_lookup", "make", "model", "canonical_part_key", unique=True),
    )

class UnrepairedClaim(Base):
    __tablename__ = "unrepaired_claims_ledger"

    ledger_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    registration_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    canonical_part_key: Mapped[str] = mapped_column(String(50), nullable=False)
    damage_class: Mapped[str] = mapped_column(String(30), nullable=False)
    settled_amount_inr: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_repaired_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

