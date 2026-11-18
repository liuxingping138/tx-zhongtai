"""thinktank-service 入口：智库（知识库，预留报告库、方案库等子库扩展）。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from platform_common.body_limit import RequestBodyLimitMiddleware
from platform_common.errors import register_exception_handlers
from platform_common.health import build_health_router
from platform_common.http_utils import MULTIPART_OVERHEAD_BYTES
from platform_common.logging_setup import get_logger, setup_logging
from platform_common.request_context import RequestIdMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.common.audit_emit import outbox_loop
from app.common.security import get_authz_client
from app.core.config import get_settings
from app.core.database import check_database_ready
from app.knowledge.api.routes import router as knowledge_router

settings = get_settings()
setup_logging(settings.service_name, level=settings.log_level, json_output=settings.environment != "development")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    task = asyncio.create_task(outbox_loop(stop, settings))
    logger.info("thinktank_service_started", environment=settings.environment)
    yield
    stop.set()
    task.cancel()
    client = get_authz_client(settings)
    await client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="thinktank-service",
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.environment != "production" else None,
        lifespan=lifespan,
    )
    max_body = max(settings.upload_max_bytes, settings.import_max_bytes) + MULTIPART_OVERHEAD_BYTES
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=max_body)
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
    app.include_router(build_health_router({"database": check_database_ready}))
    app.include_router(knowledge_router)
    return app


app = create_app()
