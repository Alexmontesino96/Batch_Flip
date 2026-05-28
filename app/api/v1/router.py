from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.amazon import router as amazon_router
from app.api.v1.analyze import router as analyze_router
from app.api.v1.auth import router as auth_router
from app.api.v1.jobs import router as jobs_router

v1_router = APIRouter()
v1_router.include_router(auth_router)
v1_router.include_router(amazon_router)
v1_router.include_router(jobs_router)
v1_router.include_router(analyze_router)
v1_router.include_router(admin_router)
