"""ai-service 入口：AI提问（提示词模板、批量任务、多轮对话）。批量执行在单独的 ai-worker 进程。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

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
from app.core.codebook import close_codebook_client
from app.core.config import get_settings
from app.core.database import check_database_ready, engine

settings = get_settings()
setup_logging(settings.service_name, level=settings.log_level, json_output=settings.environment != "development")
logger = get_logger(__name__)

DEFAULT_MAX_BYTES = 2 * 1024 * 1024
# 政策打标一批（/internal/v1/pipeline-runs）把每条政策的正文放在一段 JSON 里，默认 1000 条、全文，
# 上传额度的 20MB 装不下（汉字一个 3 字节），超了回 413、类型判断天天失败、进度不动。
# 这个前缀网关上没有路由，只有政策服务调得到；政策服务按 PIPELINE_ROWS_BUDGET 截短每批，留出余量。
PIPELINE_MAX_BYTES = 64 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    stop = asyncio.Event()
    task = asyncio.create_task(outbox_loop(stop, settings))
    logger.info("ai_service_started", environment=settings.environment)
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await close_codebook_client()
        client = get_authz_client(settings)
        await client.aclose()
        await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="ai-service",
        version="0.1.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.environment != "production" else None,
        lifespan=lifespan,
    )
    upload_limit = settings.upload_max_bytes + MULTIPART_OVERHEAD_BYTES
    # RequestIdMiddleware 最后注册（最外层先执行），保证 401/413 截断同样携带 request_id。
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=DEFAULT_MAX_BYTES,
        exact_limits={
            "/api/v1/ai/batch-runs": upload_limit,
            "/api/v1/ai/batch-runs/input-preview": upload_limit,
        },
        path_limits={"/internal/v1/pipeline-runs": PIPELINE_MAX_BYTES},
        suffix_limits={
            "/files/excel": upload_limit,
            "/files/code": upload_limit,
        },
        upload_paths=("/api/v1/ai/batch-runs",),
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
    app.include_router(prompts_router)
    app.include_router(batch_runs_router)
    app.include_router(model_configs_router)
    app.include_router(billing_router)
    app.include_router(stream_router)
    app.include_router(internal_router)
    return app


app = create_app()
