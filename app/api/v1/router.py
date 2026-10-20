from fastapi import APIRouter
from app.api.v1.endpoints.claims_router import router as claims_router
from app.api.v1.endpoints.demo_router import router as demo_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(claims_router)
api_v1_router.include_router(demo_router)

