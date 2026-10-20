from dataclasses import asdict
import json
import threading
from typing import Any, Dict, List, Optional
from app.domain.claim_intent.schemas import DynamicDamageClass, DynamicPartClass


class DynamicTaxonomyRegistry:
    """Dynamic, in-memory taxonomy registry for vehicle parts and damage classes.

    Classes are NOT hardcoded in rigid static structures:
    - New part and damage classes can be registered dynamically via `register_part_class()` and `register_damage_class()`.
    - Can be initialized from database records, JSON/YAML configurations, or external metadata stores.
    - Maintains fast reverse alias indices for instant colloquial and synonym lookups.
    """

    def __init__(self, seed_defaults: bool = True):
        self._lock = threading.RLock()
        self._parts: Dict[str, DynamicPartClass] = {}
        self._damages: Dict[str, DynamicDamageClass] = {}
        self._alias_to_part_key: Dict[str, str] = {}
        self._alias_to_damage_key: Dict[str, str] = {}

        if seed_defaults:
            self._seed_default_classes()

    def register_part_class(self, part: DynamicPartClass) -> None:
        """Dynamically registers or updates a vehicle part class."""
        with self._lock:
            self._parts[part.canonical_key] = part
            canonical_normalized = part.canonical_key.lower().strip()
            self._alias_to_part_key[canonical_normalized] = part.canonical_key
            self._alias_to_part_key[canonical_normalized.replace("_", " ")] = part.canonical_key

            if part.display_name:
                self._alias_to_part_key[part.display_name.lower().strip()] = part.canonical_key

            for alias in part.aliases:
                norm = alias.lower().strip()
                if norm:
                    self._alias_to_part_key[norm] = part.canonical_key

    def register_damage_class(self, damage: DynamicDamageClass) -> None:
        """Dynamically registers or updates a damage class."""
        with self._lock:
            self._damages[damage.canonical_key] = damage
            canonical_normalized = damage.canonical_key.lower().strip()
            self._alias_to_damage_key[canonical_normalized] = damage.canonical_key
            self._alias_to_damage_key[canonical_normalized.replace("_", " ")] = damage.canonical_key

            if damage.display_name:
                self._alias_to_damage_key[damage.display_name.lower().strip()] = damage.canonical_key

            for alias in damage.aliases:
                norm = alias.lower().strip()
                if norm:
                    self._alias_to_damage_key[norm] = damage.canonical_key

    def get_part(self, canonical_key: str) -> Optional[DynamicPartClass]:
        with self._lock:
            return self._parts.get(canonical_key)

    def get_damage(self, canonical_key: str) -> Optional[DynamicDamageClass]:
        with self._lock:
            return self._damages.get(canonical_key)

    def get_part_by_alias(self, phrase: str) -> Optional[DynamicPartClass]:
        with self._lock:
            key = self._alias_to_part_key.get(phrase.lower().strip())
            return self._parts.get(key) if key else None

    def get_damage_by_alias(self, phrase: str) -> Optional[DynamicDamageClass]:
        with self._lock:
            key = self._alias_to_damage_key.get(phrase.lower().strip())
            return self._damages.get(key) if key else None

    def list_parts(self) -> List[DynamicPartClass]:
        with self._lock:
            return list(self._parts.values())

    def list_damages(self) -> List[DynamicDamageClass]:
        with self._lock:
            return list(self._damages.values())

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """Populates or extends registry from a dictionary structure."""
        with self._lock:
            for p_dict in data.get("parts", []):
                self.register_part_class(
                    DynamicPartClass(
                        canonical_key=p_dict["canonical_key"],
                        display_name=p_dict.get("display_name", p_dict["canonical_key"]),
                        side=p_dict.get("side"),
                        position=p_dict.get("position"),
                        is_safety_critical=p_dict.get("is_safety_critical", False),
                        aliases=p_dict.get("aliases", []),
                        metadata=p_dict.get("metadata", {}),
                    )
                )
            for d_dict in data.get("damages", []):
                self.register_damage_class(
                    DynamicDamageClass(
                        canonical_key=d_dict["canonical_key"],
                        display_name=d_dict.get("display_name", d_dict["canonical_key"]),
                        severity_rank=d_dict.get("severity_rank", 5),
                        is_linear=d_dict.get("is_linear", False),
                        is_safety_critical=d_dict.get("is_safety_critical", False),
                        aliases=d_dict.get("aliases", []),
                        metadata=d_dict.get("metadata", {}),
                    )
                )

    def export_to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "parts": [asdict(p) for p in self._parts.values()],
                "damages": [asdict(d) for d in self._damages.values()],
            }

    def _seed_default_classes(self) -> None:
        """Default seed covering standard Carparts and CarDD with comprehensive synonyms."""
        # --- CARPARTS (23 Classes) ---
        default_parts = [
            DynamicPartClass(
                canonical_key="front_bumper",
                display_name="Front Bumper",
                position="FRONT",
                aliases=["front bumper", "front fender cover", "front bar", "nose cone", "front bullbar"],
            ),
            DynamicPartClass(
                canonical_key="back_bumper",
                display_name="Rear Bumper",
                position="REAR",
                aliases=["rear bumper", "back bumper", "rear guard", "back guard", "tail bumper", "rear bumper bar"],
            ),
            DynamicPartClass(
                canonical_key="hood",
                display_name="Bonnet / Hood",
                position="FRONT",
                aliases=["hood", "bonnet", "engine cover", "front hood"],
            ),
            DynamicPartClass(
                canonical_key="trunk",
                display_name="Trunk Lid",
                position="REAR",
                aliases=["trunk", "boot", "rear trunk", "trunk lid", "boot lid"],
            ),
            DynamicPartClass(
                canonical_key="tailgate",
                display_name="Rear Tailgate",
                position="REAR",
                aliases=["tailgate", "rear tailgate", "hatch", "rear hatch", "liftgate"],
            ),
            DynamicPartClass(
                canonical_key="front_door",
                display_name="Front Door (Generic)",
                position="FRONT",
                aliases=["front door"],
            ),
            DynamicPartClass(
                canonical_key="front_left_door",
                display_name="Front Left Door Panel",
                side="LEFT",
                position="FRONT",
                aliases=[
                    "front left door", "front driver door", "driver side door", "driver door",
                    "driver-side door", "left front door", "fl door", "lhs front door",
                    "drivers door", "driver's side door", "drivers side door", "left driver door"
                ],
            ),
            DynamicPartClass(
                canonical_key="front_right_door",
                display_name="Front Right Door Panel",
                side="RIGHT",
                position="FRONT",
                aliases=[
                    "front right door", "front passenger door", "passenger side door", "passenger door",
                    "passenger-side door", "right front door", "fr door", "rhs front door",
                    "passengers door", "passenger's side door"
                ],
            ),
            DynamicPartClass(
                canonical_key="back_door",
                display_name="Rear Door (Generic)",
                position="REAR",
                aliases=["back door", "rear door"],
            ),
            DynamicPartClass(
                canonical_key="back_left_door",
                display_name="Rear Left Door Panel",
                side="LEFT",
                position="REAR",
                aliases=[
                    "back left door", "rear left door", "rear driver side door", "left rear door",
                    "back driver side door", "rl door", "lhs rear door", "left back door"
                ],
            ),
            DynamicPartClass(
                canonical_key="back_right_door",
                display_name="Rear Right Door Panel",
                side="RIGHT",
                position="REAR",
                aliases=[
                    "back right door", "rear right door", "rear passenger side door", "right rear door",
                    "back passenger side door", "rr door", "rhs rear door", "right back door"
                ],
            ),
            DynamicPartClass(
                canonical_key="left_mirror",
                display_name="Left Outside Rear View Mirror",
                side="LEFT",
                aliases=[
                    "left mirror", "left side mirror", "driver side mirror", "driver mirror",
                    "side mirror on left", "left orvm", "wing mirror left", "left wing mirror",
                    "side view mirror on left", "lhs mirror"
                ],
            ),
            DynamicPartClass(
                canonical_key="right_mirror",
                display_name="Right Outside Rear View Mirror",
                side="RIGHT",
                aliases=[
                    "right mirror", "right side mirror", "passenger side mirror", "passenger mirror",
                    "side mirror on right", "right orvm", "wing mirror right", "right wing mirror",
                    "side view mirror on right", "rhs mirror"
                ],
            ),
            DynamicPartClass(
                canonical_key="front_light",
                display_name="Front Headlight (Generic)",
                position="FRONT",
                aliases=["headlight", "headlamp", "front light"],
            ),
            DynamicPartClass(
                canonical_key="front_left_light",
                display_name="Front Left Headlamp",
                side="LEFT",
                position="FRONT",
                aliases=[
                    "front left light", "front left headlight", "left headlight", "left headlamp",
                    "driver side headlight", "lhs headlight", "driver headlamp"
                ],
            ),
            DynamicPartClass(
                canonical_key="front_right_light",
                display_name="Front Right Headlamp",
                side="RIGHT",
                position="FRONT",
                aliases=[
                    "front right light", "front right headlight", "right headlight", "right headlamp",
                    "passenger side headlight", "rhs headlight", "passenger headlamp"
                ],
            ),
            DynamicPartClass(
                canonical_key="back_light",
                display_name="Rear Tail Lamp (Generic)",
                position="REAR",
                aliases=["taillight", "tail lamp", "back light", "rear light", "tail light"],
            ),
            DynamicPartClass(
                canonical_key="back_left_light",
                display_name="Rear Left Tail Lamp",
                side="LEFT",
                position="REAR",
                aliases=[
                    "back left light", "rear left tail light", "rear left light", "left tail light",
                    "left taillight", "left rear lamp", "lhs tail lamp", "back left tail lamp"
                ],
            ),
            DynamicPartClass(
                canonical_key="back_right_light",
                display_name="Rear Right Tail Lamp",
                side="RIGHT",
                position="REAR",
                aliases=[
                    "back right light", "rear right tail light", "rear right light", "right tail light",
                    "right taillight", "right rear lamp", "rhs tail lamp", "back right tail lamp",
                    "rear right tail lamp"
                ],
            ),
            DynamicPartClass(
                canonical_key="front_glass",
                display_name="Front Windshield Glass",
                position="FRONT",
                is_safety_critical=True,
                aliases=[
                    "front glass", "windshield", "windscreen", "front windscreen",
                    "front windshield", "laminated windshield"
                ],
            ),
            DynamicPartClass(
                canonical_key="back_glass",
                display_name="Rear Windshield Glass",
                position="REAR",
                is_safety_critical=True,
                aliases=[
                    "back glass", "rear glass", "rear windshield", "rear windscreen",
                    "back windscreen", "rear defogger glass"
                ],
            ),
            DynamicPartClass(
                canonical_key="wheel",
                display_name="Wheel & Tire Assembly",
                is_safety_critical=True,
                aliases=[
                    "wheel", "tire", "tyre", "alloy wheel", "rim", "front wheel", "rear wheel"
                ],
            ),
        ]

        # --- CARDD (6 Damage Classes) ---
        default_damages = [
            DynamicDamageClass(
                canonical_key="scratch",
                display_name="Scratch / Scuff",
                severity_rank=6,
                is_linear=True,
                aliases=[
                    "scratch", "scratched", "keyed", "someone keyed", "scuff", "scuffed",
                    "scrape", "scraped", "paint scratch", "surface mark", "abrasion",
                    "deep scratch", "minor scratch", "swirl mark"
                ],
            ),
            DynamicDamageClass(
                canonical_key="dent",
                display_name="Dent / Impression",
                severity_rank=5,
                is_linear=False,
                aliases=[
                    "dent", "dented", "ding", "dinged", "impression", "pressed in",
                    "pushed in", "hail dent", "crease", "buckle", "minor dent", "large dent"
                ],
            ),
            DynamicDamageClass(
                canonical_key="crack",
                display_name="Crack / Fracture",
                severity_rank=4,
                is_linear=True,
                aliases=[
                    "crack", "cracked", "fracture", "fractured", "hairline crack",
                    "split", "fissure", "cleft", "snapped"
                ],
            ),
            DynamicDamageClass(
                canonical_key="lamp_broken",
                display_name="Broken Lamp / Light",
                severity_rank=3,
                is_linear=False,
                aliases=[
                    "lamp broken", "broken light", "broken lamp", "tail light broken",
                    "headlight broken", "smashed light", "cracked lens", "smashed lamp",
                    "shattered light", "broken headlamp", "broken taillight"
                ],
            ),
            DynamicDamageClass(
                canonical_key="glass_shatter",
                display_name="Shattered Glass",
                severity_rank=2,
                is_linear=False,
                is_safety_critical=True,
                aliases=[
                    "glass shatter", "shattered glass", "broken glass", "glass broken",
                    "shattered windshield", "smashed window", "spiderweb glass",
                    "shattered", "shattered window"
                ],
            ),
            DynamicDamageClass(
                canonical_key="tire_flat",
                display_name="Flat Tire / Puncture",
                severity_rank=1,
                is_linear=False,
                is_safety_critical=True,
                aliases=[
                    "tire flat", "flat tire", "flat tyre", "punctured tire",
                    "blown tire", "burst tyre", "punctured", "tire puncture"
                ],
            ),
        ]

        for p in default_parts:
            self.register_part_class(p)

        for d in default_damages:
            self.register_damage_class(d)


_GLOBAL_REGISTRY: Optional[DynamicTaxonomyRegistry] = None


def get_default_taxonomy_registry() -> DynamicTaxonomyRegistry:
    """Singleton getter for the global DynamicTaxonomyRegistry."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = DynamicTaxonomyRegistry(seed_defaults=True)
    return _GLOBAL_REGISTRY
