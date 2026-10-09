"""健康检查路由构建器。

`/health/live`：进程存活，不检查任何依赖。
`/health/ready`：检查本服务直接依赖（数据库、Redis 等），
不递归调用下游服务，避免级联超时（架构文档第 11.2 节）。

这两个路径只在服务内部/容器网络可用，网关不应为其配置公开路由。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

ReadinessCheck = Callable[[], Awaitable[bool]]


def build_health_router(readiness_checks: dict[str, ReadinessCheck] | None = None) -> APIRouter:
    """构建健康检查路由。

    :param readiness_checks: 名称到异步检查函数的映射，函数返回 True 表示该依赖就绪。
    """

    router = APIRouter(tags=["health"])
    checks = readiness_checks or {}

    @router.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @router.get("/health/ready")
    async def ready() -> JSONResponse:
        results: dict[str, bool] = {}
        for name, check in checks.items():
            try:
                results[name] = await check()
            except Exception:  # noqa: BLE001  依赖检查失败即标记未就绪，不向上抛出
                results[name] = False

        healthy = all(results.values()) if results else True
        payload = {"status": "ready" if healthy else "not_ready", "checks": results}
        return JSONResponse(
            status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload,
        )

    return router
