"""iam-service 入口。P3：认证、会话、权限引擎与公共管理 API。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from platform_common.errors import register_exception_handlers
from platform_common.health import build_health_router
from platform_common.logging_setup import get_logger, setup_logging
from platform_common.request_context import RequestIdMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.internal import router as internal_router
from app.api.system import router as system_router
from app.core.config import get_settings
from app.core.database import check_database_ready
from app.core.jwt_keys import ensure_jwt_keys
from app.core.redis_client import check_redis_ready

settings = get_settings()
setup_logging(settings.service_name, level=settings.log_level, json_output=settings.environment != "development")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ensure_jwt_keys(settings.jwt_keys_path, allow_generate=settings.allow_generate_jwt_keys)
    logger.info("iam_service_started", environment=settings.environment)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="iam-service",
        version="0.3.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.environment != "production" else None,
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware)
    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)
    app.include_router(
        build_health_router(
            {
                "database": check_database_ready,
                "redis": check_redis_ready,
            }
        )
    )
    app.include_router(auth_router)
    app.include_router(system_router)
    app.include_router(internal_router)
    return app


app = create_app()
