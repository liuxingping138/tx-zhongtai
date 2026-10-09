"""在应用读取请求体之前限制体积，并拦住没有身份的上传。

FastAPI 把 ``UploadFile`` 放进路由参数时，会在权限依赖返回之前就把 multipart
写进临时文件。上传路由改为进入函数后再解析；这里再挡一层：声明了超限
Content-Length 的请求不会进入应用，没有 Bearer 的上传也不会开始读正文。
没有 Content-Length 的流式正文由读取端逐块计数。
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from platform_common.errors import ErrorCode

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

_UPLOAD_SUFFIXES = ("/import", "/resolve")


def _headers(scope: Scope) -> dict[str, str]:
    found: dict[str, str] = {}
    for key, value in scope.get("headers") or []:
        found[key.decode("latin1").lower()] = value.decode("latin1")
    return found


def _is_upload(scope: Scope) -> bool:
    path = (scope.get("path") or "").rstrip("/")
    return scope.get("method") == "POST" and path.endswith(_UPLOAD_SUFFIXES)


async def _json_response(send: Send, status: int, code: str, message: str) -> None:
    body = json.dumps(
        {"code": code, "message": message, "data": None, "request_id": None},
        ensure_ascii=False,
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class RequestBodyLimitMiddleware:
    """按字节拒绝过大的请求。上传路径在缺少 Bearer 时直接 401，不读取正文。"""

    def __init__(self, app: Any, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = _headers(scope)
        if _is_upload(scope) and not headers.get("authorization", "").lower().startswith("bearer "):
            await _json_response(send, 401, ErrorCode.AUTH_UNAUTHENTICATED, "未认证或凭据已失效")
            return
        raw_length = headers.get("content-length")
        if raw_length:
            try:
                length = int(raw_length)
            except ValueError:
                length = -1
            if length > self.max_bytes:
                await _json_response(send, 413, ErrorCode.VALIDATION_ERROR, "请求体过大")
                return
        await self.app(scope, receive, send)
