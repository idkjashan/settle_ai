import time
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.session import get_db_session
from app.infrastructure.db.repositories import DemoResetRepository
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

