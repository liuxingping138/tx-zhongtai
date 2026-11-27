"""thinktank-service 入口：智库（资料库、报告库、方案库、我的收藏）。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import Depends, FastAPI
from platform_common.body_limit import RequestBodyLimitMiddleware
from platform_common.errors import register_exception_handlers
from platform_common.health import build_health_router
from platform_common.http_utils import MULTIPART_OVERHEAD_BYTES
from platform_common.logging_setup import get_logger, setup_logging
from platform_common.request_context import RequestIdMiddleware
from starlette.middleware.cors import CORSMiddleware

from app.access.api.guard import require_trusted_network
from app.access.api.routes import router as whitelist_router
from app.common.audit_emit import outbox_loop
from app.common.codebook_client import close_codebook_client
from app.common.security import get_authz_client
from app.core.config import get_settings
from app.core.database import check_database_ready, engine
from app.core.storage import close_storage_client
from app.favorites.api.routes import router as favorites_router
from app.knowledge.api.routes import router as knowledge_router
from app.library.api.routes import proposals_router, reports_router

settings = get_settings()
setup_logging(settings.service_name, level=settings.log_level, json_output=settings.environment != "development")
logger = get_logger(__name__)

DEFAULT_MAX_BYTES = 2 * 1024 * 1024


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    task = asyncio.create_task(outbox_loop(stop, settings))
    logger.info("thinktank_service_started", environment=settings.environment)
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await close_storage_client()
        await close_codebook_client()
        client = get_authz_client(settings)
        await client.aclose()
        await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="thinktank-service",
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.environment != "production" else None,
        lifespan=lifespan,
    )
    upload_limit = settings.upload_max_bytes + MULTIPART_OVERHEAD_BYTES
    import_limit = settings.import_max_bytes + MULTIPART_OVERHEAD_BYTES
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=DEFAULT_MAX_BYTES,
        path_limits={
            "/api/v1/thinktank/knowledge/upload": upload_limit,
            "/api/v1/thinktank/knowledge/upload-tags": import_limit,
            "/api/v1/thinktank/reports/upload": upload_limit,
            "/api/v1/thinktank/reports/upload-tags": import_limit,
            "/api/v1/thinktank/proposals/upload": upload_limit,
            "/api/v1/thinktank/proposals/upload-tags": import_limit,
        },
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
    app.include_router(build_health_router({"database": check_database_ready}))
    # 资料库、报告库、方案库、我的收藏只在公司网络或有效白名单下可用；白名单维护接口不挂（见 access/api/routes.py）。
    network_guard = [Depends(require_trusted_network)]
    app.include_router(knowledge_router, dependencies=network_guard)
    app.include_router(reports_router, dependencies=network_guard)
    app.include_router(proposals_router, dependencies=network_guard)
    app.include_router(favorites_router, dependencies=network_guard)
    app.include_router(whitelist_router)
    return app


app = create_app()
