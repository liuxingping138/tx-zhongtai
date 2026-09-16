"""请求辅助：客户端 IP、User-Agent 脱敏、JSON 成功响应。"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from platform_common.request_context import get_request_id
from platform_common.responses import ApiResponse


def client_ip(request: Request) -> str:
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
