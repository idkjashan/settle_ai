from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import logger
from app.api.v1.router import api_v1_router
from app.infrastructure.db.seed import seed_database
from app.infrastructure.cache.redis_manager import redis_manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Auto-Settle AI backend starting up...")
    # Pre-seed DB tables & records if needed
    try:
        await seed_database()
    except Exception as e:
        logger.warning(f"Database seed check failed (might already be initialized): {e}")

    yield

    logger.info("Auto-Settle AI backend shutting down...")
    await redis_manager.close()

app = FastAPI(
    title="Auto-Settle AI",
    description="Autonomous Video-to-Cash Claims Adjuster API",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router)

@app.get("/health")
async def health_check():
    return {"status": "HEALTHY", "version": "2.1.0"}

