"""请求辅助：客户端 IP、User-Agent 脱敏、JSON 成功响应。"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from platform_common.request_context import get_request_id
from platform_common.responses import ApiResponse


def client_ip(request: Request) -> str:
    """取客户端 IP，用于登录限流和审计留痕。

    这里无条件信任 X-Forwarded-For 的第一段，成立的前提是**服务只能经网关访问**：
    Traefik 默认会丢弃客户端自带的 X-Forwarded-*，由它自己重写（已实测，
    伪造 `X-Forwarded-For: 203.0.113.99` 不会进到这里）。

    因此 iam-service 的端口不得直接对外暴露，也不要在网关前再加一层
    未做同样清洗的代理——否则攻击者可以自行构造该头，绕过按 IP 的登录限流
    并污染审计里的来源 IP。部署约束见 docs/部署与维护.md。
    """

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return "unknown"


def client_user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:200]


def success_json(data: Any = None, *, status_code: int = 200, message: str = "success") -> JSONResponse:
    body = ApiResponse(code="OK", message=message, data=data, request_id=get_request_id())
    return JSONResponse(status_code=status_code, content=body.model_dump())
