import asyncio
import json
from pathlib import Path
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional
from uuid import UUID
from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.exceptions import Stage2Error
from app.domain.dual_mask_segmentation.interfaces import (
    ICatalogAndLedgerGrounder,
    IDualModelInferencer,
    IPartSideResolverAndGrouper,
    IPolygonIntersectionEngine,
    ISoMCropRenderer,
)
from app.domain.dual_mask_segmentation.schemas import (
    DiscardedSpilloverHit,
    GroundedDamagedPart,
    GroupedPartCandidate,
    Stage3HandoffPayload,
)
from app.domain.vehicle_identity_continuity.schemas import Stage2HandoffPayload
from app.infrastructure.db.models import Claim
from app.core.logging import logger


class DualMaskSegmentationOrchestrator:
    """Coordinates Stage 2 Dual-Mask Segmentation:
    1. Batched FP16 GPU inference (Carparts-Seg + CarDD-Seg) under GPU semaphore
    2. Shapely GEOS polygon intersection, spillover filtering & completeness check
    3. Trajectory side resolution & dual-frame selection (Zoom Anti-Inflation)
    4. PostgreSQL OEM catalogue & unrepaired ledger verification (ESC-03..07)
    5. Non-occluding 15px-dilated Set-of-Marks (SoM) crop & SVG rendering
    6. State commit & Redis SSE event publication
    """

    def __init__(
        self,
        db_session: AsyncSession,
        redis_client: Redis,
        gpu_semaphore: asyncio.Semaphore,
        inferencer: IDualModelInferencer,
        intersection_engine: IPolygonIntersectionEngine,
        grouper: IPartSideResolverAndGrouper,
        catalog_grounder: ICatalogAndLedgerGrounder,
        som_renderer: ISoMCropRenderer,
        settings: Optional[Stage2Settings] = None,
    ):
        self.db = db_session
        self.redis = redis_client
        self.gpu_semaphore = gpu_semaphore
        self.inferencer = inferencer
        self.intersection_engine = intersection_engine
        self.grouper = grouper
        self.catalog_grounder = catalog_grounder
        self.som_renderer = som_renderer
        self.settings = settings or Stage2Settings()

    async def execute(self, payload: Stage2HandoffPayload) -> Stage3HandoffPayload:
        t_start = time.perf_counter()
        latencies: Dict[str, float] = {}
        discarded_hits: List[DiscardedSpilloverHit] = []
        evaluated_kf_count = len(payload.keyframe_paths)

        # Resolve optional claim_intent from payload
        raw_intent = getattr(payload, "claim_intent", None)
        claim_intent = None
        if raw_intent is not None:
            if hasattr(raw_intent, "claimed_parts"):
                claim_intent = raw_intent
            elif isinstance(raw_intent, dict):
                from app.domain.claim_intent.schemas import ClaimIntent
                claim_intent = ClaimIntent(
                    raw_text=raw_intent.get("raw_text", ""),
                    claimed_parts=raw_intent.get("claimed_parts", []),
                    claimed_damages=raw_intent.get("claimed_damages", []),
                    is_empty=raw_intent.get("is_empty", False),
                )
            elif isinstance(raw_intent, str) and raw_intent.strip():
                from app.domain.claim_intent.intent_grounder import get_claim_intent_grounder
                claim_intent = get_claim_intent_grounder().ground(raw_intent)

        unclaimed_candidates: List[GroupedPartCandidate] = []

        try:
            # Step 1 & 2: Batched GPU Inference under shared GPU lock
            t_gpu = time.perf_counter()
            async with self.gpu_semaphore:
                frame_predictions, loaded_frames_bgr = await asyncio.to_thread(
                    self.inferencer.infer_keyframes, payload.keyframe_paths
                )
            latencies["dual_gpu_infer_ms"] = round((time.perf_counter() - t_gpu) * 1000, 2)
            evaluated_kf_count = len(frame_predictions)

            # Step 3 & 4: Shapely Spatial Intersection & Trajectory Grouping
            t_geo = time.perf_counter()
            intersections, discarded_hits, unclipped_areas = await asyncio.to_thread(
                self.intersection_engine.compute_intersections, frame_predictions, claim_intent
            )
            candidates = await asyncio.to_thread(
                self.grouper.resolve_and_group, intersections, frame_predictions, unclipped_areas, claim_intent
            )
            latencies["shapely_and_grouping_ms"] = round((time.perf_counter() - t_geo) * 1000, 2)

            # Conditioned Stage 2 Evaluation:
            # Filter and prioritize detections matching user's claimed intent
            has_explicit_intent = (
                claim_intent is not None
                and not getattr(claim_intent, "is_empty", False)
                and (bool(getattr(claim_intent, "claimed_parts", [])) or bool(getattr(claim_intent, "claimed_damages", [])))
            )

            if has_explicit_intent:
                claimed_candidates: List[GroupedPartCandidate] = []
                for c in candidates:
                    if getattr(c, "is_claimed", True):
                        claimed_candidates.append(c)
                    else:
                        unclaimed_candidates.append(c)

                # If user claimed specific damage, but none of the detected panels matched the claimed intent:
                if not claimed_candidates:
                    from app.domain.dual_mask_segmentation.exceptions import Stage2ClaimedDamageNotFoundError
                    claimed_summary = f"parts={getattr(claim_intent, 'claimed_parts', [])}, damages={getattr(claim_intent, 'claimed_damages', [])}"
                    raise Stage2ClaimedDamageNotFoundError(
                        message=f"Claimed damage ({claimed_summary}) was not detected on camera. Routing to manual adjuster review.",
                        failure_codes=["ESC-07_CLAIMED_DAMAGE_NOT_FOUND"],
                    )
                target_candidates = claimed_candidates
            else:
                target_candidates = candidates

            # Step 5: Async SQL OEM Catalogue & Unrepaired Ledger Grounding
            t_sql = time.perf_counter()
            grounding_res = await self.catalog_grounder.ground_and_check_guardrails(
                payload.policy_id, target_candidates
            )
            latencies["sql_grounding_ms"] = round((time.perf_counter() - t_sql) * 1000, 2)

            # Step 6: Render 15px-Dilated SoM Crops & Normalized SVG Overlays
            t_som = time.perf_counter()
            grounded_parts = await asyncio.to_thread(
                self.som_renderer.render_artifacts,
                payload.claim_id,
                grounding_res.verified_pairs,
                loaded_frames_bgr,
            )
            latencies["som_render_ms"] = round((time.perf_counter() - t_som) * 1000, 2)

            latencies["total_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            telemetry = self._build_telemetry(
                passed=True,
                escalation_code=None,
                failure_codes=[],
                latencies=latencies,
                evaluated_kf_count=evaluated_kf_count,
                grounded_parts=grounded_parts,
                discarded_hits=discarded_hits,
                claim_intent=claim_intent,
                unclaimed_candidates=unclaimed_candidates,
            )

            await self._commit_success(payload.claim_id, telemetry)
            await self._publish_sse_success(payload.claim_id, grounded_parts)

            return Stage3HandoffPayload(
                claim_id=payload.claim_id,
                policy_id=payload.policy_id,
                registration_number=grounding_res.registration_number,
                make=grounding_res.make,
                model=grounding_res.model,
                grounded_parts=grounded_parts,
                telemetry=telemetry,
                claim_intent=claim_intent,
                unclaimed_preexisting_parts=unclaimed_candidates,
            )

        except Stage2Error as err:
            latencies["total_ms"] = round((time.perf_counter() - t_start) * 1000, 2)
            telemetry = self._build_telemetry(
                passed=False,
                escalation_code=err.escalation_code,
                failure_codes=err.failure_codes,
                latencies=latencies,
                evaluated_kf_count=evaluated_kf_count,
                grounded_parts=[],
                discarded_hits=discarded_hits,
                claim_intent=claim_intent,
                unclaimed_candidates=unclaimed_candidates,
            )
            await self._commit_escalation(
                payload.claim_id, err.escalation_code, err.failure_codes, telemetry
            )
            await self._publish_sse_failure(
                payload.claim_id, err.escalation_code, err.failure_codes, err.message
            )
            raise

    @staticmethod
    def _build_telemetry(
        passed: bool,
        escalation_code: Optional[str],
        failure_codes: List[str],
        latencies: Dict[str, float],
        evaluated_kf_count: int,
        grounded_parts: List[GroundedDamagedPart],
        discarded_hits: List[DiscardedSpilloverHit],
        claim_intent: Optional[Any] = None,
        unclaimed_candidates: Optional[List[GroupedPartCandidate]] = None,
    ) -> dict:
        serialized_parts = []
        for gp in grounded_parts:
            d = asdict(gp)
            d["som_annotated_crop_path"] = str(gp.som_annotated_crop_path)
            d["som_raw_crop_path"] = str(gp.som_raw_crop_path)
            serialized_parts.append(d)

        serialized_unclaimed = []
        for u in (unclaimed_candidates or []):
            serialized_unclaimed.append({
                "canonical_part_key": getattr(u, "canonical_part_key", "unknown"),
                "primary_damage_class": getattr(u, "primary_damage_class", "unknown"),
                "detected_damage_classes": getattr(u, "detected_damage_classes", []),
                "final_iop_ratio": getattr(u, "final_iop_ratio", 0.0),
                "part_confidence": getattr(u, "part_confidence", 0.0),
                "damage_confidence": getattr(u, "damage_confidence", 0.0),
                "claim_status": "UNCLAIMED_PREEXISTING_DAMAGE",
            })

        claim_intent_dict = None
        if claim_intent is not None:
            if hasattr(claim_intent, "__dataclass_fields__"):
                claim_intent_dict = asdict(claim_intent)
            elif isinstance(claim_intent, dict):
                claim_intent_dict = claim_intent

        return {
            "schema_version": "2.0.0",
            "stage_passed": passed,
            "escalation_code": escalation_code,
            "failure_codes": failure_codes,
            "latency_ms": latencies,
            "evaluated_keyframes_count": evaluated_kf_count,
            "opposite_side_multi_hit_detected": escalation_code == "ESC-05",
            "safety_critical_damage_detected": escalation_code == "ESC-06",
            "unrepaired_repeat_claim_detected": escalation_code == "ESC-03",
            "claimed_damage_not_found": escalation_code == "ESC-07_CLAIMED_DAMAGE_NOT_FOUND",
            "claim_intent": claim_intent_dict,
            "unclaimed_preexisting_damages": serialized_unclaimed,
            "unclaimed_candidates": serialized_unclaimed,
            "unclaimed_preexisting_damage_detected": len(serialized_unclaimed) > 0,
            "grounded_damaged_parts": serialized_parts,
            "discarded_spillover_hits": [asdict(h) for h in discarded_hits],
        }

    async def _commit_success(self, claim_id: UUID, telemetry: dict) -> None:
        stmt = (
            update(Claim)
            .where(Claim.claim_id == claim_id)
            .values(
                current_stage="STAGE_3_VLM_INSPECTION",
                claim_status="PROCESSING",
                escalation_code=None,
                failure_codes=[],
                dual_mask_telemetry=telemetry,
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def _commit_escalation(
        self, claim_id: UUID, escalation_code: str, failure_codes: List[str], telemetry: dict
    ) -> None:
        stmt = (
            update(Claim)
            .where(Claim.claim_id == claim_id)
            .values(
                current_stage="STAGE_2_SEGMENTATION",
                claim_status="ESCALATED",
                escalation_code=escalation_code,
                failure_codes=failure_codes,
                dual_mask_telemetry=telemetry,
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def _publish_sse_success(
        self, claim_id: UUID, grounded_parts: List[GroundedDamagedPart]
    ) -> None:
        if not self.redis:
            return
        payload = {
            "event": "STAGE_2_PASSED",
            "claim_id": str(claim_id),
            "damaged_parts": [
                {
                    "canonical_part_key": p.canonical_part_key,
                    "display_part_name": p.display_part_name,
                    "oem_part_number": p.oem_part_number,
                    "primary_damage_class": p.primary_damage_class,
                    "iop_percentage": p.iop_percentage,
                }
                for p in grounded_parts
            ],
        }
        try:
            await self.redis.publish(f"claim:events:{claim_id}", json.dumps(payload))
        except Exception:
            pass

    async def _publish_sse_failure(
        self, claim_id: UUID, escalation_code: str, failure_codes: List[str], msg: str
    ) -> None:
        if not self.redis:
            return
        payload = {
            "event": "STAGE_2_FAILED",
            "claim_id": str(claim_id),
            "escalation_code": escalation_code,
            "failure_codes": failure_codes,
            "user_message": msg,
        }
        try:
            await self.redis.publish(f"claim:events:{claim_id}", json.dumps(payload))
        except Exception:
            pass


_shared_stage2_gpu_semaphore: Optional[asyncio.Semaphore] = None
_shared_stage2_inferencer: Optional[IDualModelInferencer] = None


def get_stage2_orchestrator(
    db_session: AsyncSession,
    redis_client: Optional[Redis] = None,
    settings: Optional[Stage2Settings] = None,
    inferencer: Optional[IDualModelInferencer] = None,
    gpu_semaphore: Optional[asyncio.Semaphore] = None,
) -> DualMaskSegmentationOrchestrator:
    """Factory creating fully-wired DualMaskSegmentationOrchestrator with singleton models."""
    global _shared_stage2_gpu_semaphore, _shared_stage2_inferencer
    cfg = settings or Stage2Settings()

    if gpu_semaphore is None:
        if _shared_stage2_gpu_semaphore is None:
            _shared_stage2_gpu_semaphore = asyncio.Semaphore(1)
        gpu_semaphore = _shared_stage2_gpu_semaphore

    if inferencer is None or settings is not None:
        if inferencer is None and (settings is not None or _shared_stage2_inferencer is None):
            from ultralytics import YOLO
            from app.domain.dual_mask_segmentation.dual_model_inferencer import DualModelInferencer
            from app.domain.dual_mask_segmentation.taxonomy import (
                CARDD_CLASS_MAP,
                CARPARTS_CLASS_MAP,
            )
            from app.domain.dual_mask_segmentation.exceptions import Stage2ModelCompatibilityError

            default_cp = Stage2Settings.model_fields["carparts_model_path"].default
            default_cd = Stage2Settings.model_fields["cardd_model_path"].default

            target_cp = Path(cfg.carparts_model_path)
            target_cd = Path(cfg.cardd_model_path)

            if not target_cp.exists():
                raise Stage2ModelCompatibilityError(
                    f"Carparts-Seg model weights not found at '{target_cp}'. "
                    f"Required: YOLO11m-seg fine-tuned on 23-class Carparts-Seg taxonomy ({len(CARPARTS_CLASS_MAP)} classes). "
                    f"Generic base weights (e.g. yolo11m-seg.pt) cannot be substituted.",
                    details={"expected_path": str(target_cp), "model_role": "Carparts-Seg"},
                )
            if not target_cd.exists():
                raise Stage2ModelCompatibilityError(
                    f"CarDD-Seg model weights not found at '{target_cd}'. "
                    f"Required: YOLO11m-seg fine-tuned on 6-class CarDD damage taxonomy ({len(CARDD_CLASS_MAP)} classes). "
                    f"Generic base weights (e.g. yolo11m-seg.pt) cannot be substituted.",
                    details={"expected_path": str(target_cd), "model_role": "CarDD-Seg"},
                )
            cp_model = YOLO(str(target_cp))
            cd_model = YOLO(str(target_cd))
            inst = DualModelInferencer(cp_model, cd_model, cfg, validate_taxonomy=True)
            if settings is None:
                _shared_stage2_inferencer = inst
            inferencer = inst
        elif inferencer is None:
            inferencer = _shared_stage2_inferencer

    from app.domain.dual_mask_segmentation.catalog_and_ledger_grounder import (
        CatalogAndLedgerGrounder,
    )
    from app.domain.dual_mask_segmentation.part_side_resolver_and_grouper import (
        PartSideResolverAndGrouper,
    )
    from app.domain.dual_mask_segmentation.polygon_intersection_engine import (
        PolygonIntersectionEngine,
    )
    from app.domain.dual_mask_segmentation.som_crop_renderer import SoMCropRenderer

    intersection_engine = PolygonIntersectionEngine(cfg)
    grouper = PartSideResolverAndGrouper(cfg)
    catalog_grounder = CatalogAndLedgerGrounder(db_session, cfg)
    som_renderer = SoMCropRenderer(cfg)

    return DualMaskSegmentationOrchestrator(
        db_session=db_session,
        redis_client=redis_client,
        gpu_semaphore=gpu_semaphore,
        inferencer=inferencer,
        intersection_engine=intersection_engine,
        grouper=grouper,
        catalog_grounder=catalog_grounder,
        som_renderer=som_renderer,
        settings=cfg,
    )

