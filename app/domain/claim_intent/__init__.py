"""Claim Intent Domain Module: Natural language claim intent grounding and dynamic taxonomy."""
from app.domain.claim_intent.schemas import (
    ClaimIntent,
    ClaimedDamageIntent,
    ClaimedDamagePartPair,
    ClaimedPartIntent,
    DynamicDamageClass,
    DynamicPartClass,
)
from app.domain.claim_intent.taxonomy_registry import (
    DynamicTaxonomyRegistry,
    get_default_taxonomy_registry,
)
from app.domain.claim_intent.intent_grounder import (
    ClaimIntentGrounder,
    get_claim_intent_grounder,
)

__all__ = [
    "ClaimIntent",
    "ClaimedDamageIntent",
    "ClaimedDamagePartPair",
    "ClaimedPartIntent",
    "DynamicDamageClass",
    "DynamicPartClass",
    "DynamicTaxonomyRegistry",
    "get_default_taxonomy_registry",
    "ClaimIntentGrounder",
    "get_claim_intent_grounder",
]
