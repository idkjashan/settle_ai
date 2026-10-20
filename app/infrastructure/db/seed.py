import asyncio
from datetime import date
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.session import engine, async_session_factory
from app.infrastructure.db.models import Base, InsuredPolicy, OemPart, UnrepairedClaim

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

def generate_scaled_parts(make: str, model: str, part_num_prefix: str, multiplier: float) -> list[OemPart]:
    m = Decimal(str(multiplier))
    parts = []
    for (key, name, pnum, mat, cost, rr, dent, paint, pdr, rep, safe) in HYUNDAI_CRETA_PARTS:
        scaled_pnum = f"{part_num_prefix}-{key[:4].upper()}"
        parts.append(
            OemPart(
                make=make,
                model=model,
                canonical_part_key=key,
                display_part_name=name,
                oem_part_number=scaled_pnum,
                part_material=mat,
                depreciation_rate_non_zero_dep=Decimal("0.00"),
                oem_part_cost_inr=(cost * m).quantize(Decimal("0.01")),
                rr_labour_inr=(rr * m).quantize(Decimal("0.01")),
                denting_base_labour_inr=(dent * m).quantize(Decimal("0.01")),
                full_panel_paint_inr=(paint * m).quantize(Decimal("0.01")),
                pdr_or_polish_flat_inr=(pdr * m).quantize(Decimal("0.01")),
                is_repairable=rep,
                is_safety_critical=safe,
            )
        )
    return parts

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

        # 3. Seed 22 Canonical OEM Parts for Hyundai Creta, Maruti Swift (0.72x), and Tata Nexon (0.85x)
        oem_parts: list[OemPart] = []
        for (key, name, pnum, mat, cost, rr, dent, paint, pdr, rep, safe) in HYUNDAI_CRETA_PARTS:
            oem_parts.append(
                OemPart(
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
            )

        oem_parts.extend(generate_scaled_parts("Maruti", "Swift", "71811-M0000", 0.72))
        oem_parts.extend(generate_scaled_parts("Tata", "Nexon", "5424-M0000", 0.85))
        session.add_all(oem_parts)

        # 4. Seed sample unrepaired claim record for double-claim prevention testing
        unrepaired = UnrepairedClaim(
            registration_number="MH12DE1433",
            canonical_part_key="back_bumper",
            damage_class="dent",
            settled_amount_inr=Decimal("4200.00"),
            is_repaired_verified=False,
        )
        session.add(unrepaired)

        await session.commit()
        print(f"Database seeding completed successfully. ({len(policies)} policies, {len(oem_parts)} OEM parts)")

if __name__ == "__main__":
    asyncio.run(seed_database())
