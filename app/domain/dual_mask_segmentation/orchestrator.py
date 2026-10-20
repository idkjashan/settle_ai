import asyncio
import json
from pathlib import Path
import time
from dataclasses import asdict
from typing import Dict, List, Optional
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
                self.intersection_engine.compute_intersections, frame_predictions
            )
            candidates = await asyncio.to_thread(
                self.grouper.resolve_and_group, intersections, frame_predictions, unclipped_areas
            )
            latencies["shapely_and_grouping_ms"] = round((time.perf_counter() - t_geo) * 1000, 2)

            # Step 5: Async SQL OEM Catalogue & Unrepaired Ledger Grounding
            t_sql = time.perf_counter()
            grounding_res = await self.catalog_grounder.ground_and_check_guardrails(
                payload.policy_id, candidates
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
    ) -> dict:
        serialized_parts = []
        for gp in grounded_parts:
            d = asdict(gp)
            d["som_annotated_crop_path"] = str(gp.som_annotated_crop_path)
            d["som_raw_crop_path"] = str(gp.som_raw_crop_path)
            serialized_parts.append(d)

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

    if inferencer is None:
        if _shared_stage2_inferencer is None:
            from ultralytics import YOLO
            from app.domain.dual_mask_segmentation.dual_model_inferencer import DualModelInferencer

            from app.domain.dual_mask_segmentation.taxonomy import (
                CARDD_CLASS_MAP,
                CARPARTS_CLASS_MAP,
            )
            from app.domain.dual_mask_segmentation.exceptions import Stage2ModelCompatibilityError

            cp_path = Path(cfg.carparts_model_path)
            cd_path = Path(cfg.cardd_model_path)
            if not cp_path.exists():
                raise Stage2ModelCompatibilityError(
                    f"Carparts-Seg model weights not found at '{cp_path}'. "
                    f"Required: YOLO11m-seg fine-tuned on 23-class Carparts-Seg taxonomy ({len(CARPARTS_CLASS_MAP)} classes). "
                    f"Generic base weights (e.g. yolo11m-seg.pt) cannot be substituted.",
                    details={"expected_path": str(cp_path), "model_role": "Carparts-Seg"},
                )
            if not cd_path.exists():
                raise Stage2ModelCompatibilityError(
                    f"CarDD-Seg model weights not found at '{cd_path}'. "
                    f"Required: YOLO11m-seg fine-tuned on 6-class CarDD damage taxonomy ({len(CARDD_CLASS_MAP)} classes). "
                    f"Generic base weights (e.g. yolo11m-seg.pt) cannot be substituted.",
                    details={"expected_path": str(cd_path), "model_role": "CarDD-Seg"},
                )
            cp_model = YOLO(str(cp_path))
            cd_model = YOLO(str(cd_path))
            _shared_stage2_inferencer = DualModelInferencer(cp_model, cd_model, cfg, validate_taxonomy=True)
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

