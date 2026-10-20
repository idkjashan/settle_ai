"""tests/claim_intent/test_taxonomy_registry.py

Verifies the Dynamic Taxonomy Architecture:
1. Default seeding includes standard 23 Carparts and 6 CarDD damage classes.
2. Novel parts can be registered dynamically at runtime without static code edits.
3. Novel damages can be registered dynamically at runtime without static code edits.
4. Alias and colloquial reverse indices update dynamically on class registration.
5. Configuration dictionaries / JSON structures can dynamically populate/extend the registry.
6. Thread-safety during concurrent class registration and lookup.
"""
import concurrent.futures
import pytest
from app.domain.claim_intent.schemas import DynamicDamageClass, DynamicPartClass
from app.domain.claim_intent.taxonomy_registry import (
    DynamicTaxonomyRegistry,
    get_default_taxonomy_registry,
)


class TestDynamicTaxonomyRegistry:
    def test_default_seeded_classes(self):
        """Registry seeds default 22 vehicle parts and 6 CarDD damage classes."""
        reg = DynamicTaxonomyRegistry(seed_defaults=True)
        parts = reg.list_parts()
        damages = reg.list_damages()

        assert len(parts) >= 22
        assert len(damages) == 6

        # Check key canonical parts
        assert reg.get_part("front_left_door") is not None
        assert reg.get_part("back_right_light") is not None
        assert reg.get_part("left_mirror") is not None
        assert reg.get_part("front_bumper") is not None
        assert reg.get_part("hood") is not None

        # Check key damages
        assert reg.get_damage("scratch") is not None
        assert reg.get_damage("dent") is not None
        assert reg.get_damage("crack") is not None
        assert reg.get_damage("lamp_broken") is not None
        assert reg.get_damage("glass_shatter") is not None
        assert reg.get_damage("tire_flat") is not None

    def test_dynamic_register_novel_part_class(self):
        """Newly trained models or vehicle platforms can register new parts at runtime."""
        reg = DynamicTaxonomyRegistry(seed_defaults=False)
        assert len(reg.list_parts()) == 0

        sunroof = DynamicPartClass(
            canonical_key="sunroof_glass",
            display_name="Panoramic Sunroof Glass Panel",
            side="CENTER",
            position="ROOF",
            is_safety_critical=True,
            aliases=["sunroof", "moonroof", "panoramic roof", "sky view glass"],
        )
        reg.register_part_class(sunroof)

        retrieved = reg.get_part("sunroof_glass")
        assert retrieved is not None
        assert retrieved.canonical_key == "sunroof_glass"
        assert retrieved.display_name == "Panoramic Sunroof Glass Panel"
        assert retrieved.is_safety_critical is True

        # Test alias lookups
        assert reg.get_part_by_alias("sunroof") == sunroof
        assert reg.get_part_by_alias("moonroof") == sunroof
        assert reg.get_part_by_alias("panoramic roof") == sunroof
        assert reg.get_part_by_alias("sky view glass") == sunroof
        assert reg.get_part_by_alias("sunroof glass") == sunroof

    def test_dynamic_register_novel_damage_class(self):
        """New damage categories (e.g., hail_dent, paint_peel, animal_bite) can be registered dynamically."""
        reg = DynamicTaxonomyRegistry(seed_defaults=False)
        assert len(reg.list_damages()) == 0

        hail = DynamicDamageClass(
            canonical_key="hail_pitting",
            display_name="Hail Storm Pitting / Dimples",
            severity_rank=5,
            is_linear=False,
            is_safety_critical=False,
            aliases=["hail damage", "hail pits", "golf ball dent", "storm dimples"],
        )
        reg.register_damage_class(hail)

        retrieved = reg.get_damage("hail_pitting")
        assert retrieved is not None
        assert retrieved.canonical_key == "hail_pitting"
        assert retrieved.severity_rank == 5

        # Test alias lookups
        assert reg.get_damage_by_alias("hail damage") == hail
        assert reg.get_damage_by_alias("golf ball dent") == hail
        assert reg.get_damage_by_alias("hail pitting") == hail

    def test_load_and_export_dict_config(self):
        """Can bulk load part and damage classes from JSON/dictionary configurations."""
        reg = DynamicTaxonomyRegistry(seed_defaults=False)
        config_data = {
            "parts": [
                {
                    "canonical_key": "running_board_left",
                    "display_name": "Left Side Footstep / Running Board",
                    "side": "LEFT",
                    "position": None,
                    "aliases": ["left footstep", "left running board", "driver side sidestep"],
                },
                {
                    "canonical_key": "rear_spoiler",
                    "display_name": "Rear Boot Lip Spoiler",
                    "side": "CENTER",
                    "position": "REAR",
                    "aliases": ["spoiler", "boot wing", "rear wing"],
                },
            ],
            "damages": [
                {
                    "canonical_key": "paint_peel",
                    "display_name": "Clearcoat Paint Peel",
                    "severity_rank": 6,
                    "is_linear": False,
                    "aliases": ["peeling paint", "clearcoat failure", "delamination"],
                }
            ],
        }

        reg.load_from_dict(config_data)
        assert reg.get_part("running_board_left") is not None
        assert reg.get_part_by_alias("driver side sidestep") is not None
        assert reg.get_part("rear_spoiler") is not None
        assert reg.get_damage("paint_peel") is not None
        assert reg.get_damage_by_alias("clearcoat failure") is not None

        exported = reg.export_to_dict()
        assert len(exported["parts"]) == 2
        assert len(exported["damages"]) == 1

    def test_thread_safety_concurrent_registration(self):
        """Concurrent threads registering and reading classes encounter zero race conditions."""
        reg = DynamicTaxonomyRegistry(seed_defaults=False)

        def worker(idx: int):
            part = DynamicPartClass(
                canonical_key=f"sensor_{idx}",
                display_name=f"Parking Radar Sensor #{idx}",
                aliases=[f"sensor {idx}", f"radar {idx}"],
            )
            reg.register_part_class(part)
            retrieved = reg.get_part(f"sensor_{idx}")
            assert retrieved is not None
            assert reg.get_part_by_alias(f"radar {idx}") is not None

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, i) for i in range(50)]
            for f in concurrent.futures.as_completed(futures):
                f.result()

        assert len(reg.list_parts()) == 50

    def test_global_singleton(self):
        """get_default_taxonomy_registry() returns a consistent pre-seeded instance."""
        reg1 = get_default_taxonomy_registry()
        reg2 = get_default_taxonomy_registry()
        assert reg1 is reg2
        assert len(reg1.list_parts()) >= 22
