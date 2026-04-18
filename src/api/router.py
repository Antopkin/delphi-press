"""Главный роутер API v1.

Спека: docs-site/docs/api/reference.md (§5.1).
"""

from fastapi import APIRouter

from src.api.auth import router as auth_router
from src.api.health import router as health_router
from src.api.keys import router as keys_router
from src.api.outlets import router as outlets_router
from src.api.predictions import router as predictions_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(keys_router, tags=["keys"])
api_router.include_router(predictions_router, tags=["predictions"])
api_router.include_router(outlets_router, tags=["outlets"])
api_router.include_router(health_router, tags=["health"])
