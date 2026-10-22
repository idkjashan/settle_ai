import time
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.session import get_db_session
from app.infrastructure.db.repositories import DemoResetRepository
from app.infrastructure.db.seed import clear_and_seed_database, seed_clean_slate
from app.infrastructure.cache.redis_manager import redis_manager
from app.core.logging import logger

router = APIRouter(prefix="/demo", tags=["demo"])

@router.post("/reset", status_code=status.HTTP_200_OK)
async def reset_demo(db: AsyncSession = Depends(get_db_session)):
    """
    Jury demo reset endpoint.
    Purges demo/rehearsal claim rows, resets POL-HAPPY-001 claim counts, and flushes Redis claim locks in < 5ms.
    """
    t0 = time.perf_counter()
    demo_repo = DemoResetRepository(db)
    db_result = await demo_repo.reset_demo_state()
    locks_cleared = await redis_manager.flush_locks()
    duration_ms = (time.perf_counter() - t0) * 1000.0

    logger.info(f"Demo reset complete: {db_result}, locks_cleared={locks_cleared} in {duration_ms:.2f}ms")

    return {
        "status": "DEMO_STATE_RESET_SUCCESS",
        "deleted_claims": db_result.get("deleted_claims", 0),
        "locks_cleared": locks_cleared,
        "duration_ms": duration_ms,
    }


@router.get("/seed", status_code=status.HTTP_200_OK)
@router.post("/seed", status_code=status.HTTP_200_OK)
async def seed_demo(claims: bool = Query(True, description="Whether to include pre-staged demo claims")):
    """
    Direct 1-click seed endpoint for hackathon judges & testers.
    Clears database and seeds policies, generic & OEM parts, and pre-staged claims
    for the 4 authentic test videos. Accessible via GET (in browser) or POST.
    Set claims=false to clear all claims and start with a fresh slate for manual video upload.
    """
    t0 = time.perf_counter()
    result = await clear_and_seed_database(clear_existing=True, include_demo_claims=claims)
    duration_ms = (time.perf_counter() - t0) * 1000.0
    result["duration_ms"] = round(duration_ms, 2)
    logger.info(f"Demo seed complete (claims={claims}) in {duration_ms:.2f}ms")
    return result


@router.get("/clean-slate", status_code=status.HTTP_200_OK)
@router.post("/clean-slate", status_code=status.HTTP_200_OK)
async def clean_slate_demo():
    """
    Cleans all claim history and reseeds policies and parts catalogue.
    Leaves 0 claims in database so user can manually upload and test any of the 4 videos cleanly.
    """
    t0 = time.perf_counter()
    result = await seed_clean_slate()
    duration_ms = (time.perf_counter() - t0) * 1000.0
    result["duration_ms"] = round(duration_ms, 2)
    logger.info(f"Clean slate seed complete in {duration_ms:.2f}ms")
    return result
