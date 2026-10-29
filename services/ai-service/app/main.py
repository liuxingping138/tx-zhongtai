"""ai-service 入口：AI提问（提示词模板、批量任务、多轮对话）。批量执行在单独的 ai-worker 进程。"""

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

from app.api.batch_runs import router as batch_runs_router
from app.api.billing import router as billing_router
from app.api.internal import router as internal_router
from app.api.model_configs import router as model_configs_router
from app.api.prompts import router as prompts_router
from app.api.security import get_authz_client
from app.api.stream import router as stream_router
from app.application.audit_emit import outbox_loop
from app.core.config import get_settings
from app.core.database import check_database_ready

settings = get_settings()
setup_logging(settings.service_name, level=settings.log_level, json_output=settings.environment != "development")
logger = get_logger(__name__)

STREAM_MAX_BYTES = 2 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    task = asyncio.create_task(outbox_loop(stop, settings))
    logger.info("ai_service_started", environment=settings.environment)
    yield
    stop.set()
    task.cancel()
    client = get_authz_client(settings)
    await client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="ai-service",
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.environment != "production" else None,
        lifespan=lifespan,
    )
    app.add_middleware(RequestIdMiddleware)
    # 流式提问只收一段 JSON（提示词最多 20 万字），用不着上传文件那么大的额度；这个前缀在网关上也不经缓冲限流。
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=settings.upload_max_bytes + MULTIPART_OVERHEAD_BYTES,
        path_limits={"/api/v1/ai/stream": STREAM_MAX_BYTES},
    )
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
    app.include_router(prompts_router)
    app.include_router(batch_runs_router)
    app.include_router(model_configs_router)
    app.include_router(billing_router)
    app.include_router(stream_router)
    app.include_router(internal_router)
    return app


app = create_app()
