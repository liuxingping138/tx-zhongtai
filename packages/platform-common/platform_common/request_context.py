"""请求 ID 上下文与中间件。

请求 ID 由网关或客户端传入的 `X-Request-Id` 透传，服务未收到时自行生成；
响应头与统一响应体 `request_id` 字段均回填同一个值，便于跨服务日志关联。
"""

from __future__ import annotations

import contextvars
import re
import uuid
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager

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


def request_id_of(request: Request) -> str | None:
    """这个请求的 ID。优先取上下文变量；取不到时读中间件挂在 request.state 上的那份。

    未捕获的异常由最外层的 ServerErrorMiddleware 交给 500 处理器，那时 RequestIdMiddleware 已经退出、
    上下文变量已经还原，get_request_id() 是 None；request.state 存在整个请求共用的 scope 里，还在。
    """

    return get_request_id() or getattr(request.state, "request_id", None)


@contextmanager
def bound_request_id(request_id: str | None) -> Iterator[None]:
    """临时把请求 ID 放回上下文变量，让这段时间里写的日志带上它（日志处理链从上下文变量取）。"""

    token = _request_id_ctx.set(request_id)
    try:
        yield
    finally:
        _request_id_ctx.reset(token)


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
