"""请求辅助：User-Agent 脱敏、JSON 成功响应。取客户端 IP 见 platform_common.http_utils.client_ip。"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from platform_common.request_context import get_request_id
from platform_common.responses import ApiResponse


def client_user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:200]


def success_json(
    data: Any = None, *, status_code: int = 200, message: str = "success", headers: dict[str, str] | None = None
) -> JSONResponse:
    body = ApiResponse(code="OK", message=message, data=data, request_id=get_request_id())
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)
