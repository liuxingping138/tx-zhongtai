"""招中标服务入口：只读源库，无迁移、回传、上传和调度任务。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from platform_common.errors import register_exception_handlers
from platform_common.health import build_health_router
from platform_common.logging_setup import setup_logging
from platform_common.request_context import RequestIdMiddleware

from app.api.routes import router
from app.api.security import get_authz_client
from app.application.counts import get_count, get_totals
from app.core.config import get_settings
from app.core.source import check_source_ready
from app.domain.queries import ListQuery

settings = get_settings()
setup_logging(settings.service_name, level=settings.log_level, json_output=settings.environment != "development")


async def warm_totals() -> None:
    # 后台预热与刷新总量与列表基准无条件计数；专用计数线程不会挤占列表筛选计数。
    while True:
        get_totals()
        for kind in ("purchaser", "winbid"):
            for status in ("1", "0"):
                get_count(kind, ListQuery(project_status=status))
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(warm_totals()) if settings.mysql_host else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await get_authz_client(settings).aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="tender-service",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        openapi_url="/openapi.json" if settings.environment != "production" else None,
        redoc_url=None,
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    app.include_router(build_health_router({"source": check_source_ready}))
    app.include_router(router)
    return app


app = create_app()
