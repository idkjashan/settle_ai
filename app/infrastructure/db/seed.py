import asyncio
from datetime import date
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.session import engine, async_session_factory
from app.infrastructure.db.models import Base, InsuredPolicy, OemPart, UnrepairedClaim

async def seed_database() -> None:
    # 1. Create tables if they do not exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        # Check if already seeded
        res = await session.get(InsuredPolicy, "POL-HAPPY-001")
        if res:
            print("Database already seeded with POL-HAPPY-001.")
            return

        print("Seeding database with test policies and OEM parts...")

        # 2. Seed Insured Policies
        policies = [
            InsuredPolicy(
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
            InsuredPolicy(
                policy_id="POL-EXPIRED-002",
                policy_status="ACTIVE",  # status says active but date expired
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
            InsuredPolicy(
                policy_id="POL-FUTURE-003",
                policy_status="ACTIVE",
                policy_start_date=date(2027, 1, 1),
                policy_end_date=date(2027, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=0,
                registration_number="KA03MJ7777",
                vin_last_6="67890C",
                make="Kia",
                model="Seltos",
                manufacturing_year=2024,
                registered_color="BLACK",
                registered_color_hsv={"h_min": 0, "h_max": 180, "s_min": 0, "s_max": 255, "v_min": 0, "v_max": 50},
                paint_type="metallic",
                zero_dep_addon=True,
                compulsory_deductible_inr=Decimal("1000.00"),
                estimated_ncb_loss_inr=Decimal("3500.00"),
            ),
            InsuredPolicy(
                policy_id="POL-CLAIMCAP-004",
                policy_status="ACTIVE",
                policy_start_date=date(2026, 1, 1),
                policy_end_date=date(2026, 12, 31),
                max_cash_claims_per_year=2,
                cash_claims_ytd=2,  # Limit reached!
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
            InsuredPolicy(
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
            InsuredPolicy(
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
        ]
        session.add_all(policies)

        # 3. Seed OEM Parts for Hyundai Creta
        oem_parts = [
            OemPart(
                make="Hyundai", model="Creta", canonical_part_key="front_bumper",
                display_part_name="Front Bumper Assembly", oem_part_number="86511-M0000",
                part_material="plastic", oem_part_cost_inr=Decimal("4500.00"),
                rr_labour_inr=Decimal("650.00"), denting_base_labour_inr=Decimal("900.00"),
                full_panel_paint_inr=Decimal("3200.00"), pdr_or_polish_flat_inr=Decimal("650.00"),
                is_repairable=True, is_safety_critical=False
            ),
            OemPart(
                make="Hyundai", model="Creta", canonical_part_key="front_left_door",
                display_part_name="Front Left Door Panel", oem_part_number="76003-M0000",
                part_material="metal", oem_part_cost_inr=Decimal("11500.00"),
                rr_labour_inr=Decimal("950.00"), denting_base_labour_inr=Decimal("1400.00"),
                full_panel_paint_inr=Decimal("4200.00"), pdr_or_polish_flat_inr=Decimal("850.00"),
                is_repairable=True, is_safety_critical=False
            ),
            OemPart(
                make="Hyundai", model="Creta", canonical_part_key="front_right_door",
                display_part_name="Front Right Door Panel", oem_part_number="76004-M0000",
                part_material="metal", oem_part_cost_inr=Decimal("11500.00"),
                rr_labour_inr=Decimal("950.00"), denting_base_labour_inr=Decimal("1400.00"),
                full_panel_paint_inr=Decimal("4200.00"), pdr_or_polish_flat_inr=Decimal("850.00"),
                is_repairable=True, is_safety_critical=False
            ),
            OemPart(
                make="Hyundai", model="Creta", canonical_part_key="left_mirror",
                display_part_name="Left Outside Rearview Mirror", oem_part_number="87610-M0000",
                part_material="assembly", oem_part_cost_inr=Decimal("3800.00"),
                rr_labour_inr=Decimal("400.00"), denting_base_labour_inr=Decimal("0.00"),
                full_panel_paint_inr=Decimal("800.00"), pdr_or_polish_flat_inr=Decimal("400.00"),
                is_repairable=False, is_safety_critical=False
            ),
            OemPart(
                make="Hyundai", model="Creta", canonical_part_key="rear_bumper",
                display_part_name="Rear Bumper Assembly", oem_part_number="86611-M0000",
                part_material="plastic", oem_part_cost_inr=Decimal("4800.00"),
                rr_labour_inr=Decimal("650.00"), denting_base_labour_inr=Decimal("900.00"),
                full_panel_paint_inr=Decimal("3200.00"), pdr_or_polish_flat_inr=Decimal("650.00"),
                is_repairable=True, is_safety_critical=False
            ),
            OemPart(
                make="Hyundai", model="Creta", canonical_part_key="hood",
                display_part_name="Engine Hood Bonnet", oem_part_number="66400-M0000",
                part_material="metal", oem_part_cost_inr=Decimal("8500.00"),
                rr_labour_inr=Decimal("850.00"), denting_base_labour_inr=Decimal("1500.00"),
                full_panel_paint_inr=Decimal("4500.00"), pdr_or_polish_flat_inr=Decimal("900.00"),
                is_repairable=True, is_safety_critical=False
            ),
            OemPart(
                make="Hyundai", model="Creta", canonical_part_key="front_windshield",
                display_part_name="Laminated Front Windshield Glass", oem_part_number="86110-M0000",
                part_material="glass", oem_part_cost_inr=Decimal("9800.00"),
                rr_labour_inr=Decimal("1200.00"), denting_base_labour_inr=Decimal("0.00"),
                full_panel_paint_inr=Decimal("0.00"), pdr_or_polish_flat_inr=Decimal("0.00"),
                is_repairable=False, is_safety_critical=True
            ),
        ]
        session.add_all(oem_parts)

        # 4. Seed sample unrepaired claim record for double-claim prevention testing
        unrepaired = UnrepairedClaim(
            registration_number="MH12DE1433",
            canonical_part_key="rear_bumper",
            damage_class="dent",
            settled_amount_inr=Decimal("4200.00"),
            is_repaired_verified=False,
        )
        session.add(unrepaired)

        await session.commit()
        print("Database seeding completed successfully.")

if __name__ == "__main__":
    asyncio.run(seed_database())

