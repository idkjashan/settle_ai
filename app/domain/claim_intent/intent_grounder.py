import difflib
import math
import re
import time
from typing import Dict, List, Optional, Set, Tuple
import numpy as np

from app.domain.claim_intent.schemas import (
    ClaimIntent,
    ClaimedDamageIntent,
    ClaimedDamagePartPair,
    ClaimedPartIntent,
)
from app.domain.claim_intent.taxonomy_registry import (
    DynamicTaxonomyRegistry,
    get_default_taxonomy_registry,
)
from app.core.logging import logger


class FastSemanticRouter:
    """Zero-shot semantic router using FastEmbed ONNX embeddings with cosine similarity.
    Falls back gracefully if weights are missing or offline.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._embedder = None
        self._is_available = False
        self._class_embeddings: Dict[str, np.ndarray] = {}
        self._target_keys: List[str] = []
        self._matrix: Optional[np.ndarray] = None
        self._init_engine()

    def _init_engine(self) -> None:
        try:
            from fastembed import TextEmbedding
            # Initialize with local cache fallback
            self._embedder = TextEmbedding(model_name=self.model_name)
            self._is_available = True
            logger.info(f"FastSemanticRouter initialized successfully with {self.model_name}.")
        except Exception as e:
            self._is_available = False
            logger.warning(f"FastSemanticRouter fallback to syntactic mode: {e}")

    @property
    def is_available(self) -> bool:
        return self._is_available

    def embed_texts(self, texts: List[str]) -> Optional[np.ndarray]:
        if not self._is_available or self._embedder is None:
            return None
        try:
            vectors = list(self._embedder.embed(texts))
            return np.array(vectors, dtype=np.float32)
        except Exception as e:
            logger.warning(f"Semantic embedding failed: {e}")
            return None

    def build_index(self, key_to_phrases: Dict[str, List[str]]) -> None:
        """Precomputes normalized embedding centroids for dynamic classes."""
        if not self._is_available:
            return

        all_phrases: List[str] = []
        mapping: List[str] = []
        for key, phrases in key_to_phrases.items():
            for p in phrases:
                all_phrases.append(p)
                mapping.append(key)

        if not all_phrases:
            return

        embs = self.embed_texts(all_phrases)
        if embs is None:
            return

        # Normalize rows
        norms = np.linalg.norm(embs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        embs = embs / norms

        # Group by canonical key and calculate mean unit vector
        key_vectors: Dict[str, List[np.ndarray]] = {}
        for key, vec in zip(mapping, embs):
            key_vectors.setdefault(key, []).append(vec)

        centroids = []
        keys = []
        for k, vecs in key_vectors.items():
            mean_vec = np.mean(vecs, axis=0)
            norm = np.linalg.norm(mean_vec)
            if norm > 0:
                mean_vec = mean_vec / norm
            centroids.append(mean_vec)
            keys.append(k)

        self._matrix = np.array(centroids, dtype=np.float32)
        self._target_keys = keys

    def match(self, query: str, threshold: float = 0.55) -> List[Tuple[str, float]]:
        """Returns list of (canonical_key, cosine_similarity) matching above threshold."""
        if not self._is_available or self._matrix is None or len(self._matrix) == 0:
            return []

        q_emb = self.embed_texts([query])
        if q_emb is None:
            return []

        q_norm = np.linalg.norm(q_emb[0])
        if q_norm == 0:
            return []
        q_vec = q_emb[0] / q_norm

        sims = np.dot(self._matrix, q_vec)
        matches = []
        for idx, score in enumerate(sims):
            if score >= threshold:
                matches.append((self._target_keys[idx], float(score)))

        matches.sort(key=lambda x: x[1], reverse=True)
        return matches


class ClaimIntentGrounder:
    """Robust, lightweight System 1 natural language damage intent grounder:
    - Runs in < 50ms (typical 2-5ms) on local CPU without paid external APIs.
    - Robustly handles colloquial user descriptions, typos, multi-damage claims, and side disambiguation.
    - Zero-shot semantic router with instant syntactic keyword and regex fallback.
    - Pairs claimed damages to claimed parts per clause.
    """

    def __init__(
        self,
        registry: Optional[DynamicTaxonomyRegistry] = None,
        driver_side_is_left: bool = True,
        use_semantic_router: bool = True,
    ):
        self.registry = registry or get_default_taxonomy_registry()
        self.driver_side_is_left = driver_side_is_left
        self.use_semantic_router = use_semantic_router
        self._semantic_router: Optional[FastSemanticRouter] = None

        if self.use_semantic_router:
            self._init_semantic_index()

    def _init_semantic_index(self) -> None:
        self._semantic_router = FastSemanticRouter()
        if self._semantic_router.is_available:
            part_map = {p.canonical_key: [p.canonical_key.replace("_", " "), p.display_name] + p.aliases for p in self.registry.list_parts()}
            damage_map = {d.canonical_key: [d.canonical_key.replace("_", " "), d.display_name] + d.aliases for d in self.registry.list_damages()}
            self._semantic_router.build_index({**part_map, **damage_map})

    def ground(self, description: Optional[str], driver_side_is_left: Optional[bool] = None) -> ClaimIntent:
        """Grounds a natural language claim description into structured ClaimIntent."""
        if driver_side_is_left is not None:
            self.driver_side_is_left = driver_side_is_left
        t_start = time.perf_counter()

        if not description or not description.strip():
            return ClaimIntent(
                raw_text="",
                claimed_parts=[],
                claimed_damages=[],
                part_intents=[],
                damage_intents=[],
                paired_intents=[],
                is_empty=True,
                extraction_latency_ms=round((time.perf_counter() - t_start) * 1000, 2),
                engine_used="NONE_EMPTY",
            )

        raw_text = description.strip()
        clauses = self._split_into_clauses(raw_text)
        global_pos = self._detect_position(raw_text.lower())
        global_side = self._detect_side(raw_text.lower())

        all_part_intents: List[ClaimedPartIntent] = []
        all_damage_intents: List[ClaimedDamageIntent] = []
        paired_intents: List[ClaimedDamagePartPair] = []

        seen_parts: Set[str] = set()
        seen_damages: Set[str] = set()

        for clause in clauses:
            c_parts, c_damages = self._extract_from_clause(
                clause, default_pos=global_pos, default_side=global_side
            )

            for p_intent in c_parts:
                if p_intent.canonical_part_key not in seen_parts:
                    all_part_intents.append(p_intent)
                    seen_parts.add(p_intent.canonical_part_key)

            for d_intent in c_damages:
                if d_intent.canonical_damage_key not in seen_damages:
                    all_damage_intents.append(d_intent)
                    seen_damages.add(d_intent.canonical_damage_key)

            # Pair up parts and damages found within the same clause
            if c_parts and c_damages:
                for p in c_parts:
                    for d in c_damages:
                        paired_intents.append(
                            ClaimedDamagePartPair(
                                part_key=p.canonical_part_key,
                                damage_key=d.canonical_damage_key,
                                confidence=round(min(p.confidence, d.confidence), 4),
                                clause_text=clause,
                            )
                        )

        # If multi-clauses yielded parts and damages but disjointly, cross-pair them
        if not paired_intents and all_part_intents and all_damage_intents:
            for p in all_part_intents:
                for d in all_damage_intents:
                    paired_intents.append(
                        ClaimedDamagePartPair(
                            part_key=p.canonical_part_key,
                            damage_key=d.canonical_damage_key,
                            confidence=round(min(p.confidence, d.confidence) * 0.9, 4),
                            clause_text=raw_text,
                        )
                    )

        claimed_parts = [p.canonical_part_key for p in all_part_intents]
        claimed_damages = [d.canonical_damage_key for d in all_damage_intents]

        latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
        engine_used = (
            "HYBRID_SEMANTIC_ROUTER"
            if (self._semantic_router and self._semantic_router.is_available)
            else "SYNTACTIC_REGEX_ROUTER"
        )

        return ClaimIntent(
            raw_text=raw_text,
            claimed_parts=claimed_parts,
            claimed_damages=claimed_damages,
            part_intents=all_part_intents,
            damage_intents=all_damage_intents,
            paired_intents=paired_intents,
            extraction_latency_ms=latency_ms,
            engine_used=engine_used,
            is_empty=False,
        )

    def _split_into_clauses(self, text: str) -> List[str]:
        # Split on conjunctions and punctuation to preserve localized damage-part pairings
        pattern = r"\b(?:and|plus|also|as well as|with|\&)\b|[;,\.\n]"
        tokens = re.split(pattern, text, flags=re.IGNORECASE)
        clauses = [t.strip() for t in tokens if t and t.strip()]
        return clauses if clauses else [text]

    def _extract_from_clause(
        self,
        clause: str,
        default_pos: Optional[str] = None,
        default_side: Optional[str] = None,
    ) -> Tuple[List[ClaimedPartIntent], List[ClaimedDamageIntent]]:
        norm = clause.lower().strip()
        parts: List[ClaimedPartIntent] = []
        damages: List[ClaimedDamageIntent] = []

        # 1. Syntactic / Colloquial Directional Rule Extraction
        side_hint = self._detect_side(norm) or default_side
        pos_hint = self._detect_position(norm) or default_pos

        # Check damages syntactically
        found_damage_keys = self._syntactic_damage_search(norm)
        for d_key, conf, matched in found_damage_keys:
            damages.append(
                ClaimedDamageIntent(
                    canonical_damage_key=d_key,
                    confidence=conf,
                    matched_phrase=matched,
                    disambiguation_source="COLLOQUIAL_SYNTACTIC_MAP",
                )
            )

        # Check parts syntactically with directional disambiguation
        found_parts = self._syntactic_part_search(norm, side_hint, pos_hint)
        for p_key, conf, matched in found_parts:
            parts.append(
                ClaimedPartIntent(
                    canonical_part_key=p_key,
                    confidence=conf,
                    matched_phrase=matched,
                    disambiguation_source="DIRECTIONAL_SYNTACTIC_MAP",
                )
            )

        # 2. Semantic Router (System 1) Augmentation if any part/damage wasn't found syntactically
        if self._semantic_router and self._semantic_router.is_available:
            semantic_matches = self._semantic_router.match(norm, threshold=0.62)
            for key, score in semantic_matches:
                # Is it a part? Only add if no part found yet or complementary
                part_cls = self.registry.get_part(key)
                if part_cls:
                    # Filter conflicting side or position hints
                    if side_hint and part_cls.side and part_cls.side != side_hint:
                        continue
                    if pos_hint and part_cls.position and part_cls.position != pos_hint:
                        continue
                    if not any(p.canonical_part_key == key for p in parts):
                        resolved_key = self._apply_directional_context(key, side_hint, pos_hint)
                        # Check resolved part doesn't conflict
                        resolved_cls = self.registry.get_part(resolved_key)
                        if resolved_cls:
                            if side_hint and resolved_cls.side and resolved_cls.side != side_hint:
                                continue
                            if pos_hint and resolved_cls.position and resolved_cls.position != pos_hint:
                                continue
                        if not any(p.canonical_part_key == resolved_key for p in parts):
                            # If parts were already found syntactically, only add semantic if high confidence (>0.75)
                            if not parts or score >= 0.75:
                                parts.append(
                                    ClaimedPartIntent(
                                        canonical_part_key=resolved_key,
                                        confidence=round(score, 4),
                                        matched_phrase=clause,
                                        disambiguation_source="SEMANTIC_SIMILARITY",
                                    )
                                )

                # Is it a damage?
                dmg_cls = self.registry.get_damage(key)
                if dmg_cls and not any(d.canonical_damage_key == key for d in damages):
                    if not damages or score >= 0.75:
                        damages.append(
                            ClaimedDamageIntent(
                                canonical_damage_key=key,
                                confidence=round(score, 4),
                                matched_phrase=clause,
                                disambiguation_source="SEMANTIC_SIMILARITY",
                            )
                        )

        # 3. Post-processing: Deduplicate and prune generic parts when specific sided exists
        parts = self._prune_conflicting_parts(parts, side_hint, pos_hint)

        # Specific domain heuristic: "broken mirror" or "broken side mirror"
        if any("mirror" in p.canonical_part_key for p in parts):
            if "broken" in norm or "cracked" in norm or "smashed" in norm:
                if not any(d.canonical_damage_key in ("crack", "glass_shatter") for d in damages):
                    damages.append(
                        ClaimedDamageIntent(
                            canonical_damage_key="crack",
                            confidence=0.85,
                            matched_phrase="broken mirror",
                            disambiguation_source="MIRROR_DOMAIN_HEURISTIC",
                        )
                    )

        return parts, damages

    def _prune_conflicting_parts(
        self, parts: List[ClaimedPartIntent], side_hint: Optional[str], pos_hint: Optional[str]
    ) -> List[ClaimedPartIntent]:
        if not parts:
            return parts

        # If side_hint is active, drop parts of opposing side
        if side_hint:
            filtered = []
            for p in parts:
                p_cls = self.registry.get_part(p.canonical_part_key)
                if p_cls and p_cls.side and p_cls.side != side_hint:
                    continue
                filtered.append(p)
            if filtered:
                parts = filtered

        # If specific sided parts exist (e.g. back_right_light), prune generic (e.g. back_light)
        sided_keys = {p.canonical_part_key for p in parts if any(s in p.canonical_part_key for s in ("left", "right"))}
        if sided_keys:
            generic_equivalents = {
                "front_light": ["front_left_light", "front_right_light"],
                "back_light": ["back_left_light", "back_right_light"],
                "front_door": ["front_left_door", "front_right_door"],
                "back_door": ["back_left_door", "back_right_door"],
            }
            parts = [
                p for p in parts
                if not (
                    p.canonical_part_key in generic_equivalents
                    and any(sk in generic_equivalents[p.canonical_part_key] for sk in sided_keys)
                )
            ]

        return parts

    def _detect_side(self, text: str) -> Optional[str]:
        # Disambiguate "driver side" vs "passenger side"
        if re.search(r"\b(?:driver['’]?s?\s*side|driver\s*door|driver\s*mirror)\b", text):
            return "LEFT" if self.driver_side_is_left else "RIGHT"
        if re.search(r"\b(?:passenger['’]?s?\s*side|passenger\s*door|passenger\s*mirror)\b", text):
            return "RIGHT" if self.driver_side_is_left else "LEFT"

        # Explicit left / right
        if re.search(r"\b(?:left|lhs|left[- ]hand|left[- ]side|on left)\b", text):
            return "LEFT"
        if re.search(r"\b(?:right|rhs|right[- ]hand|right[- ]side|on right)\b", text):
            return "RIGHT"
        return None

    def _detect_position(self, text: str) -> Optional[str]:
        if re.search(r"\b(?:rear|back|behind|tail)\b", text):
            return "REAR"
        if re.search(r"\b(?:front|fore)\b", text):
            return "FRONT"
        return None

    def _syntactic_damage_search(self, text: str) -> List[Tuple[str, float, str]]:
        found = []
        # Check all registered damages
        for dmg in self.registry.list_damages():
            for alias in dmg.aliases:
                pattern = r"\b" + re.escape(alias) + r"\b"
                if re.search(pattern, text):
                    found.append((dmg.canonical_key, 0.95, alias))
                    break

        # Typo tolerance via word difflib close matches for primary damage words
        if not found:
            words = re.findall(r"\b[a-z]{3,}\b", text)
            damage_words = {
                "keyed": "scratch",
                "scratch": "scratch",
                "scratched": "scratch",
                "scuff": "scratch",
                "dent": "dent",
                "dented": "dent",
                "ding": "dent",
                "crack": "crack",
                "cracked": "crack",
                "shatter": "glass_shatter",
                "shattered": "glass_shatter",
                "puncture": "tire_flat",
                "punctured": "tire_flat",
            }
            for w in words:
                matches = difflib.get_close_matches(w, list(damage_words.keys()), n=1, cutoff=0.75)
                if matches:
                    d_key = damage_words[matches[0]]
                    found.append((d_key, 0.80, w))
                    break

        return found

    def _syntactic_part_search(
        self, text: str, side_hint: Optional[str], pos_hint: Optional[str]
    ) -> List[Tuple[str, float, str]]:
        found = []

        # 1. Exact alias match against registry (longest phrases first, side-compatible)
        alias_matches = []
        for part in self.registry.list_parts():
            if side_hint and part.side and part.side != side_hint:
                continue
            if pos_hint and part.position and part.position != pos_hint:
                continue
            for alias in part.aliases:
                pattern = r"\b" + re.escape(alias) + r"\b"
                if re.search(pattern, text):
                    alias_matches.append((len(alias), part.canonical_key, 0.98, alias))

        if alias_matches:
            alias_matches.sort(key=lambda x: x[0], reverse=True)
            best_len = alias_matches[0][0]
            seen = set()
            for length, k, conf, al in alias_matches:
                if k not in seen and length >= best_len - 3:
                    seen.add(k)
                    found.append((k, conf, al))
            return found

        # 2. Compositional matching: [position] + [side] + [generic component]
        # e.g., "rear right tail light", "rear bumper", "side mirror on left", "front glass"
        comps = [
            ("bumper", ["front_bumper", "back_bumper"]),
            ("door", ["front_left_door", "front_right_door", "back_left_door", "back_right_door"]),
            ("mirror", ["left_mirror", "right_mirror"]),
            ("light", ["front_left_light", "front_right_light", "back_left_light", "back_right_light"]),
            ("lamp", ["front_left_light", "front_right_light", "back_left_light", "back_right_light"]),
            ("headlight", ["front_left_light", "front_right_light"]),
            ("tail light", ["back_left_light", "back_right_light"]),
            ("taillight", ["back_left_light", "back_right_light"]),
            ("glass", ["front_glass", "back_glass"]),
            ("windshield", ["front_glass"]),
            ("windscreen", ["front_glass"]),
            ("bonnet", ["hood"]),
            ("hood", ["hood"]),
            ("trunk", ["trunk"]),
            ("boot", ["trunk"]),
            ("tailgate", ["tailgate"]),
            ("wheel", ["wheel"]),
            ("tire", ["wheel"]),
            ("tyre", ["wheel"]),
        ]

        for token, cand_keys in comps:
            pattern = r"\b" + re.escape(token) + r"\b"
            if re.search(pattern, text):
                selected = self._resolve_candidates(cand_keys, side_hint, pos_hint)
                if selected:
                    found.append((selected, 0.90, token))
                    break

        # 3. Typo fuzzy match on primary vehicle parts
        if not found:
            words = re.findall(r"\b[a-z]{3,}\b", text)
            part_tokens = [c[0] for c in comps]
            for w in words:
                close = difflib.get_close_matches(w, part_tokens, n=1, cutoff=0.75)
                if close:
                    cand_keys = next(k for t, k in comps if t == close[0])
                    selected = self._resolve_candidates(cand_keys, side_hint, pos_hint)
                    if selected:
                        found.append((selected, 0.75, w))
                        break

        return found

    def _resolve_candidates(
        self, candidate_keys: List[str], side: Optional[str], pos: Optional[str]
    ) -> Optional[str]:
        if len(candidate_keys) == 1:
            return candidate_keys[0]

        filtered = list(candidate_keys)
        if pos == "FRONT":
            filtered = [k for k in filtered if "front" in k or "hood" in k] or filtered
        elif pos == "REAR":
            filtered = [k for k in filtered if "back" in k or "rear" in k or "tail" in k or "trunk" in k] or filtered

        if side == "LEFT":
            left_filtered = [k for k in filtered if "left" in k]
            if left_filtered:
                return left_filtered[0]
        elif side == "RIGHT":
            right_filtered = [k for k in filtered if "right" in k]
            if right_filtered:
                return right_filtered[0]

        return filtered[0] if filtered else candidate_keys[0]

    def _apply_directional_context(
        self, generic_key: str, side: Optional[str], pos: Optional[str]
    ) -> str:
        part = self.registry.get_part(generic_key)
        if not part:
            return generic_key

        # If already explicit sided, keep it
        if part.side in ("LEFT", "RIGHT"):
            return generic_key

        if "door" in generic_key:
            target_pos = pos or part.position or "FRONT"
            target_side = side or "LEFT"
            p_prefix = "front" if target_pos == "FRONT" else "back"
            s_name = "left" if target_side == "LEFT" else "right"
            candidate = f"{p_prefix}_{s_name}_door"
            if self.registry.get_part(candidate):
                return candidate

        if "light" in generic_key:
            target_pos = pos or part.position or "FRONT"
            target_side = side or "LEFT"
            p_prefix = "front" if target_pos == "FRONT" else "back"
            s_name = "left" if target_side == "LEFT" else "right"
            candidate = f"{p_prefix}_{s_name}_light"
            if self.registry.get_part(candidate):
                return candidate

        return generic_key


_GLOBAL_GROUNDER: Optional[ClaimIntentGrounder] = None


def get_claim_intent_grounder() -> ClaimIntentGrounder:
    global _GLOBAL_GROUNDER
    if _GLOBAL_GROUNDER is None:
        _GLOBAL_GROUNDER = ClaimIntentGrounder()
    return _GLOBAL_GROUNDER
