"""请求 ID 上下文与中间件。

请求 ID 由网关或客户端传入的 `X-Request-Id` 透传，服务未收到时自行生成；
响应头与统一响应体 `request_id` 字段均回填同一个值，便于跨服务日志关联。
"""

from __future__ import annotations

import contextvars
import re
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-Id"
# 审计事件的 request_id 最长 64 字；客户端传来的 ID 不合格就自己生成，
# 否则这次操作的审计事件会被审计服务拒收，等于谁都能让自己的操作不进操作日志。
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

_request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """获取当前请求上下文中的请求 ID；未在请求处理流程中调用时返回 None。"""

    return _request_id_ctx.get()


def new_request_id() -> str:
    return uuid.uuid4().hex


class RequestIdMiddleware(BaseHTTPMiddleware):
    """为每个请求生成/透传请求 ID，写入上下文变量并回填响应头。"""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if REQUEST_ID_PATTERN.match(incoming) else new_request_id()
        token = _request_id_ctx.set(request_id)
        try:
            request.state.request_id = request_id
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
