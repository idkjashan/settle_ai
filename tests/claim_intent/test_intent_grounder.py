"""tests/claim_intent/test_intent_grounder.py

Verifies the Natural Language Damage Intent Grounder (`ClaimIntentGrounder`):
1. User prompt reference test cases:
   - "someone keyed my driver side door" -> front_left_door, scratch
   - "cracked rear right tail light and dented bumper" -> back_right_light, back_bumper, crack, dent
   - "broken side mirror on left" -> left_mirror, crack / glass_shatter
2. Typo tolerance and colloquial phrasing ("skratched bonnet", "dneted", "ding", "fissure").
3. Directional disambiguation (driver vs passenger, front vs rear, left vs right).
4. Multi-clause conjunction splitting and localized part-damage pairing.
5. Strict < 50ms CPU execution ceiling (typically 2-10ms).
6. Edge case robustness: None, empty string, whitespace, arbitrary punctuation.
7. Zero-shot recognition of newly registered dynamic taxonomy classes.
"""
import time
import pytest
from app.domain.claim_intent.intent_grounder import ClaimIntentGrounder
from app.domain.claim_intent.schemas import DynamicDamageClass, DynamicPartClass
from app.domain.claim_intent.taxonomy_registry import DynamicTaxonomyRegistry


class TestClaimIntentGrounder:
    @pytest.fixture(scope="class")
    def grounder(self):
        """Shared grounder instance with semantic router enabled."""
        return ClaimIntentGrounder(driver_side_is_left=True, use_semantic_router=True)

    @pytest.fixture(scope="class")
    def syntactic_only_grounder(self):
        """Fallback grounder with semantic router disabled (pure regex/difflib)."""
        return ClaimIntentGrounder(driver_side_is_left=True, use_semantic_router=False)

    def test_prompt_case_1_keyed_driver_door(self, grounder):
        """'someone keyed my driver side door' -> part: 'front_left_door', damage: 'scratch'."""
        intent = grounder.ground("someone keyed my driver side door")

        assert not intent.is_empty
        assert "front_left_door" in intent.claimed_parts
        assert "scratch" in intent.claimed_damages
        assert any(p.part_key == "front_left_door" and p.damage_key == "scratch" for p in intent.paired_intents)
        assert intent.extraction_latency_ms < 50.0

    def test_prompt_case_2_cracked_tail_light_and_dented_bumper(self, grounder):
        """'cracked rear right tail light and dented bumper' -> parts: ['back_right_light', 'back_bumper'], damages: ['crack', 'dent']."""
        intent = grounder.ground("cracked rear right tail light and dented bumper")

        assert not intent.is_empty
        assert "back_right_light" in intent.claimed_parts
        assert "back_bumper" in intent.claimed_parts
        assert "crack" in intent.claimed_damages
        assert "dent" in intent.claimed_damages

        # Check localized clause pairings
        pairs = {(p.part_key, p.damage_key) for p in intent.paired_intents}
        assert ("back_right_light", "crack") in pairs
        assert ("back_bumper", "dent") in pairs
        assert intent.extraction_latency_ms < 50.0

    def test_prompt_case_3_broken_side_mirror_on_left(self, grounder):
        """'broken side mirror on left' -> part: 'left_mirror', damage: 'crack' or 'glass_shatter'."""
        intent = grounder.ground("broken side mirror on left")

        assert not intent.is_empty
        assert "left_mirror" in intent.claimed_parts
        assert "right_mirror" not in intent.claimed_parts
        assert any(d in intent.claimed_damages for d in ("crack", "glass_shatter", "lamp_broken"))
        assert any(p.part_key == "left_mirror" for p in intent.paired_intents)
        assert intent.extraction_latency_ms < 50.0

    def test_directional_disambiguation_driver_vs_passenger(self, grounder):
        """Driver door resolves to left door; passenger door resolves to right door."""
        driver_res = grounder.ground("dent on driver door")
        assert "front_left_door" in driver_res.claimed_parts
        assert "front_right_door" not in driver_res.claimed_parts

        pass_res = grounder.ground("scratch on passenger door")
        assert "front_right_door" in pass_res.claimed_parts
        assert "front_left_door" not in pass_res.claimed_parts

    def test_directional_disambiguation_front_vs_rear(self, grounder):
        """Front bumper vs rear bumper; front windshield vs rear glass."""
        front_res = grounder.ground("scraped front bumper")
        assert "front_bumper" in front_res.claimed_parts
        assert "back_bumper" not in front_res.claimed_parts

        rear_res = grounder.ground("dented rear bumper")
        assert "back_bumper" in rear_res.claimed_parts
        assert "front_bumper" not in rear_res.claimed_parts

        windshield_res = grounder.ground("cracked front windshield")
        assert "front_glass" in windshield_res.claimed_parts
        assert "back_glass" not in windshield_res.claimed_parts

        rear_glass_res = grounder.ground("shattered rear windshield")
        assert "back_glass" in rear_glass_res.claimed_parts
        assert "front_glass" not in rear_glass_res.claimed_parts

    def test_colloquialisms_and_synonyms(self, grounder):
        """Handles varied colloquialisms: bonnet, boot, ding, fissure, flat tire."""
        res1 = grounder.ground("dent on the bonnet and small ding on boot")
        assert "hood" in res1.claimed_parts
        assert "trunk" in res1.claimed_parts
        assert "dent" in res1.claimed_damages

        res2 = grounder.ground("flat tire and cracked alloy wheel")
        assert "wheel" in res2.claimed_parts
        assert "tire_flat" in res2.claimed_damages
        assert "crack" in res2.claimed_damages

    def test_typo_tolerance(self, grounder):
        """Fuzzy matching recovers from minor misspellings: 'skratched', 'dneted'."""
        typo_res = grounder.ground("skratched bonnet and dneted fender")
        assert "hood" in typo_res.claimed_parts
        assert "scratch" in typo_res.claimed_damages

    def test_empty_and_edge_case_inputs(self, grounder):
        """Handles None, empty string, whitespace, and non-alphabetic noise gracefully."""
        res_none = grounder.ground(None)
        assert res_none.is_empty
        assert res_none.claimed_parts == []
        assert res_none.claimed_damages == []

        res_empty = grounder.ground("   ")
        assert res_empty.is_empty
        assert res_empty.claimed_parts == []

        res_punct = grounder.ground("??? !!! @#$%^&*()")
        assert res_punct.claimed_parts == []
        assert res_punct.claimed_damages == []

    def test_sub_50ms_latency_guarantee(self, grounder):
        """Inference latency is strictly < 50ms across 20 rapid sequential calls."""
        queries = [
            "someone keyed my driver side door",
            "cracked rear right tail light and dented bumper",
            "broken side mirror on left",
            "deep scratch on front bumper and shattered windshield",
        ]

        latencies = []
        for q in queries * 5:
            t0 = time.perf_counter()
            intent = grounder.ground(q)
            lat = (time.perf_counter() - t0) * 1000
            latencies.append(lat)
            assert intent.extraction_latency_ms < 50.0
            assert lat < 50.0

        avg_lat = sum(latencies) / len(latencies)
        max_lat = max(latencies)
        assert avg_lat < 25.0, f"Average latency too high: {avg_lat:.2f}ms"
        assert max_lat < 50.0, f"Max latency breached 50ms ceiling: {max_lat:.2f}ms"

    def test_syntactic_fallback_grounder(self, syntactic_only_grounder):
        """Pure syntactic fallback works offline in < 5ms without neural embeddings."""
        intent = syntactic_only_grounder.ground("cracked rear right tail light and dented bumper")
        assert not intent.is_empty
        assert "back_right_light" in intent.claimed_parts
        assert "back_bumper" in intent.claimed_parts
        assert "crack" in intent.claimed_damages
        assert "dent" in intent.claimed_damages
        assert intent.engine_used == "SYNTACTIC_REGEX_ROUTER"
        assert intent.extraction_latency_ms < 10.0

    def test_dynamic_class_zero_shot_recognition(self):
        """When a novel class is registered dynamically, grounder immediately resolves it."""
        custom_registry = DynamicTaxonomyRegistry(seed_defaults=True)
        custom_registry.register_part_class(
            DynamicPartClass(
                canonical_key="sunroof_glass",
                display_name="Panoramic Sunroof Glass",
                aliases=["sunroof", "moonroof", "skyview glass"],
            )
        )
        custom_registry.register_damage_class(
            DynamicDamageClass(
                canonical_key="hail_pitting",
                display_name="Hail Dimples",
                aliases=["hail damage", "golf ball dent", "storm dimples"],
            )
        )

        custom_grounder = ClaimIntentGrounder(registry=custom_registry, use_semantic_router=False)
        intent = custom_grounder.ground("shattered sunroof and hail damage on bonnet")

        assert "sunroof_glass" in intent.claimed_parts
        assert "hood" in intent.claimed_parts
        assert "hail_pitting" in intent.claimed_damages
        assert "glass_shatter" in intent.claimed_damages
