from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DynamicPartClass:
    """Represents a dynamically registrable vehicle part class."""
    canonical_key: str
    display_name: str
    side: Optional[str] = None  # "LEFT", "RIGHT", "CENTER", or None
    position: Optional[str] = None  # "FRONT", "REAR", "ROOF", or None
    is_safety_critical: bool = False
    aliases: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DynamicDamageClass:
    """Represents a dynamically registrable damage class."""
    canonical_key: str
    display_name: str
    severity_rank: int = 5  # Lower number = higher actuarial severity
    is_linear: bool = False  # e.g., scratch, crack (length based)
    is_safety_critical: bool = False  # e.g., glass_shatter, tire_flat
    aliases: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClaimedPartIntent:
    canonical_part_key: str
    confidence: float
    matched_phrase: str
    disambiguation_source: str  # e.g., "EXACT_SYNONYM", "SEMANTIC_SIMILARITY", "DIRECTIONAL_RESOLVED"


@dataclass
class ClaimedDamageIntent:
    canonical_damage_key: str
    confidence: float
    matched_phrase: str
    disambiguation_source: str  # e.g., "EXACT_SYNONYM", "SEMANTIC_SIMILARITY", "COLLOQUIAL_MAP"


@dataclass
class ClaimedDamagePartPair:
    part_key: str
    damage_key: str
    confidence: float
    clause_text: str = ""


def is_damage_matching(detected_damage: str, claimed_damage: str) -> bool:
    """Returns True if detected damage class matches or is colloquially compatible with claimed damage."""
    if detected_damage == claimed_damage:
        return True
    DAMAGE_COMPATIBILITY = {
        "scratch": {"scratch", "crack", "dent", "lamp_broken"},
        "crack": {"crack", "scratch", "lamp_broken", "glass_shatter", "dent"},
        "dent": {"dent", "crack", "scratch"},
        "lamp_broken": {"lamp_broken", "crack", "scratch"},
        "glass_shatter": {"glass_shatter", "crack"},
        "tire_flat": {"tire_flat"},
    }
    return detected_damage in DAMAGE_COMPATIBILITY.get(claimed_damage, {claimed_damage})


def is_part_matching(part_a: str, part_b: str) -> bool:
    """Taxonomy-aware check whether two part classes match.
    Handles generic-to-sided parts (e.g. 'front_door' to 'front_left_door') and token subsets.
    """
    if part_a == part_b:
        return True
    if not part_a or not part_b:
        return False

    generic_to_sided = {
        "front_door": {"front_left_door", "front_right_door"},
        "back_door": {"back_left_door", "back_right_door"},
        "front_light": {"front_left_light", "front_right_light"},
        "back_light": {"back_left_light", "back_right_light"},
    }
    if part_a in generic_to_sided and part_b in generic_to_sided[part_a]:
        return True
    if part_b in generic_to_sided and part_a in generic_to_sided[part_b]:
        return True

    tokens_a = set(part_a.split("_"))
    tokens_b = set(part_b.split("_"))
    if tokens_a.issubset(tokens_b) or tokens_b.issubset(tokens_a):
        # Prevent opposing sides or opposite ends from matching
        if ("left" in tokens_a and "right" in tokens_b) or ("right" in tokens_a and "left" in tokens_b):
            return False
        if ("front" in tokens_a and "back" in tokens_b) or ("back" in tokens_a and "front" in tokens_b):
            return False
        return True

    return False


@dataclass
class ClaimIntent:
    """Structured damage intent extracted from user's natural language claim description."""
    raw_text: str
    claimed_parts: List[str] = field(default_factory=list)
    claimed_damages: List[str] = field(default_factory=list)
    part_intents: List[ClaimedPartIntent] = field(default_factory=list)
    damage_intents: List[ClaimedDamageIntent] = field(default_factory=list)
    paired_intents: List[ClaimedDamagePartPair] = field(default_factory=list)
    unclaimed_damage_handling: str = "UNCLAIMED_PREEXISTING_DAMAGE"
    extraction_latency_ms: float = 0.0
    engine_used: str = "HYBRID_SEMANTIC_ROUTER"
    is_empty: bool = False

    def matches_part(self, canonical_part_key: str) -> bool:
        """Returns True if the part matches claimed_parts (or if no parts were specified)."""
        if not self.claimed_parts:
            return True
        return any(is_part_matching(canonical_part_key, cp) for cp in self.claimed_parts)

    def matches_damage(self, damage_class: str) -> bool:
        """Returns True if the damage class matches claimed_damages (or if no damages were specified)."""
        if not self.claimed_damages:
            return True
        return any(is_damage_matching(damage_class, cd) for cd in self.claimed_damages)

    def matches_part_and_damage(self, canonical_part_key: str, damage_class: str) -> bool:
        """Returns True if this part and damage match claimed intent."""
        if not self.claimed_parts and not self.claimed_damages:
            return True
        if self.paired_intents:
            for pair in self.paired_intents:
                if is_part_matching(canonical_part_key, pair.part_key) and (
                    not pair.damage_key or is_damage_matching(damage_class, pair.damage_key)
                ):
                    return True
            return False
        part_ok = self.matches_part(canonical_part_key)
        damage_ok = self.matches_damage(damage_class)
        return part_ok and damage_ok
