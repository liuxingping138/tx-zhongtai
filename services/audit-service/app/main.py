"""audit-service 入口：内部写入、授权查询、健康检查。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from platform_common.errors import register_exception_handlers
from platform_common.health import build_health_router
from platform_common.logging_setup import get_logger, setup_logging
from platform_common.request_context import RequestIdMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.api.events import router as events_router
from app.api.internal import router as internal_router
from app.api.scheduled_jobs import router as scheduled_jobs_router
from app.api.security import get_authz_client
from app.core.config import get_settings
from app.core.database import check_database_ready, engine

settings = get_settings()
setup_logging(settings.service_name, level=settings.log_level, json_output=settings.environment != "development")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("audit_service_started", environment=settings.environment)
    try:
        yield
    finally:
        client = get_authz_client(settings)
        await client.aclose()
        await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="audit-service",
        version="0.5.0",
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
            }
        )
    )
    app.include_router(internal_router)
    app.include_router(events_router)
    app.include_router(scheduled_jobs_router)
    return app


app = create_app()
