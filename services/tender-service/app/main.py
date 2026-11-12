"""招中标服务入口：只读源库，无迁移、回传、上传和调度任务。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from platform_common.errors import register_exception_handlers
from platform_common.health import build_health_router
from platform_common.logging_setup import setup_logging
from platform_common.request_context import RequestIdMiddleware

from app.api.routes import router
from app.api.security import get_authz_client
from app.core.config import get_settings
from app.core.source import check_source_ready

settings = get_settings()
setup_logging(settings.service_name, level=settings.log_level, json_output=settings.environment != "development")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
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
