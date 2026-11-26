"""在应用读取请求体之前限制体积，并拦住没有身份的上传。

FastAPI 把 ``UploadFile`` 放进路由参数时，会在权限依赖返回之前就把 multipart
写进临时文件；JSON 正文也是先整段读进内存、再跑鉴权依赖。这里挡在应用前面：
声明了超限 Content-Length 的请求不会进入应用，没有 Bearer 的上传也不会开始读正文；
不带 Content-Length 的分块（chunked）正文按实际收到的字节累计，一超就停、回 413，
否则未登录的人发几路大正文就能把服务内存打满。
"""

from __future__ import annotations

import json

from fastapi import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from platform_common.errors import ErrorCode
from platform_common.request_context import REQUEST_ID_HEADER, REQUEST_ID_PATTERN, get_request_id

_UPLOAD_SUFFIXES = (
    "/import",
    "/resolve",
    "/files/excel",
    "/files/code",
    "/upload",
    "/upload-tags",
    "/input-preview",
)


def _headers(scope: Scope) -> dict[str, str]:
    found: dict[str, str] = {}
    for key, value in scope.get("headers") or []:
        found[key.decode("latin1").lower()] = value.decode("latin1")
    return found


def _is_upload(scope: Scope, upload_paths: frozenset[str] = frozenset()) -> bool:
    path = (scope.get("path") or "").rstrip("/")
    return scope.get("method") == "POST" and (path.endswith(_UPLOAD_SUFFIXES) or path in upload_paths)


def _resolve_request_id(headers: dict[str, str]) -> str | None:
    current = get_request_id()
    if current:
        return current
    incoming = (headers.get("x-request-id") or "").strip()
    return incoming if REQUEST_ID_PATTERN.match(incoming) else None


async def _json_response(send: Send, status: int, code: str, message: str, *, request_id: str | None = None) -> None:
    body = json.dumps(
        {"code": code, "message": message, "data": None, "request_id": request_id},
        ensure_ascii=False,
    ).encode("utf-8")
    resp_headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if request_id:
        resp_headers.append((REQUEST_ID_HEADER.lower().encode("ascii"), request_id.encode("ascii")))
    await send({"type": "http.response.start", "status": status, "headers": resp_headers})
    await send({"type": "http.response.body", "body": body})


class RequestBodyTooLargeError(HTTPException):
    """读正文时超了上限。FastAPI 读正文出的错会被包成 400「解析失败」，只有 HTTPException 原样往外抛，所以继承它。"""

    def __init__(self) -> None:
        super().__init__(status_code=413, detail=_TOO_LARGE)


_TOO_LARGE = "请求体过大"


class RequestBodyLimitMiddleware:
    """按字节拒绝过大的请求。上传路径在缺少 Bearer 时直接 401，不读取正文。

    默认 ``max_bytes`` 按普通 JSON 请求收窄；需要更大额度的上传或内部接口通过
    ``exact_limits`` / ``path_limits``（按最长路径前缀匹配）/ ``suffix_limits`` 单独放宽。
    """

    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int,
        path_limits: dict[str, int] | None = None,
        *,
        exact_limits: dict[str, int] | None = None,
        suffix_limits: dict[str, int] | None = None,
        upload_paths: tuple[str, ...] = (),
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.exact_limits = {path.rstrip("/"): limit for path, limit in (exact_limits or {}).items()}
        # 按前缀长度降序匹配，避免 /upload 抢先命中 /upload-tags 等更长路径。
        self.path_limits = sorted(
            ((prefix.rstrip("/"), limit) for prefix, limit in (path_limits or {}).items()),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        self.suffix_limits = sorted(
            ((suffix.rstrip("/"), limit) for suffix, limit in (suffix_limits or {}).items()),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        self.upload_paths = frozenset(path.rstrip("/") for path in upload_paths)

    def _limit(self, scope: Scope) -> int:
        path = (scope.get("path") or "").rstrip("/")
        if path in self.exact_limits:
            return self.exact_limits[path]
        for prefix, limit in self.path_limits:
            if path == prefix or path.startswith(f"{prefix}/"):
                return limit
        for suffix, limit in self.suffix_limits:
            if path.endswith(suffix):
                return limit
        return self.max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = _headers(scope)
        rid = _resolve_request_id(headers)
        if _is_upload(scope, self.upload_paths) and not headers.get("authorization", "").lower().startswith("bearer "):
            await _json_response(send, 401, ErrorCode.AUTH_UNAUTHENTICATED, "未认证或凭据已失效", request_id=rid)
            return
        limit = self._limit(scope)
        if _declared_length(headers) > limit:
            await _json_response(send, 413, ErrorCode.VALIDATION_ERROR, _TOO_LARGE, request_id=rid)
            return
        await self._counted(scope, receive, send, limit, rid)

    async def _counted(self, scope: Scope, receive: Receive, send: Send, limit: int, request_id: str | None) -> None:
        """按实际收到的字节累计，一超就停：不带 Content-Length 的分块正文靠这一层挡。"""

        received = 0
        started = False

        async def counted_receive() -> Message:
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise RequestBodyTooLargeError
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal started
            started = started or message.get("type") == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counted_receive, tracked_send)
        except RequestBodyTooLargeError:
            # 应用的异常处理没接住（比如在中间件层读的正文）：还没开始回响应就由这里回 413。
            if not started:
                await _json_response(send, 413, ErrorCode.VALIDATION_ERROR, _TOO_LARGE, request_id=request_id)


def _declared_length(headers: dict[str, str]) -> int:
    try:
        return int(headers.get("content-length") or -1)
    except ValueError:
        return -1
