"""系统管理路由聚合。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.ip_whitelist import router as ip_whitelist_router
from app.api.roles import router as roles_router
from app.api.sessions import router as sessions_router
from app.api.users import router as users_router

router = APIRouter(prefix="/api/v1/system", tags=["system"])
router.include_router(users_router)
router.include_router(roles_router)
router.include_router(sessions_router)
router.include_router(ip_whitelist_router)
