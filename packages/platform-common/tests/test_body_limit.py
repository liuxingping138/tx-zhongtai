"""请求体上限在进入应用之前生效，上传缺少身份时不读取正文。"""

from __future__ import annotations

import pytest

from platform_common.body_limit import RequestBodyLimitMiddleware


async def _ok_app(scope, receive, send):  # type: ignore[no-untyped-def]
    message = await receive()
    body = message.get("body", b"")
    payload = b'{"code":"OK","message":"success","data":null,"request_id":null}'
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": payload})
    scope["seen"] = body


@pytest.mark.asyncio
async def test_content_length_over_limit_never_calls_app() -> None:
    called = False

    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True
        await receive()

    middleware = RequestBodyLimitMiddleware(app, max_bytes=8)
    sent: list[dict[str, object]] = []

    async def send(message):  # type: ignore[no-untyped-def]
        sent.append(message)

    async def receive():  # type: ignore[no-untyped-def]
        raise AssertionError("不应读取正文")

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/policy/sources/import",
        "headers": [
            (b"content-length", b"21"),
            (b"authorization", b"Bearer token"),
        ],
    }
    await middleware(scope, receive, send)
    assert called is False
    assert sent[0]["status"] == 413


@pytest.mark.asyncio
async def test_upload_without_bearer_returns_401_without_reading() -> None:
    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        raise AssertionError("未认证上传不应进入应用")

    middleware = RequestBodyLimitMiddleware(app, max_bytes=1024)
    sent: list[dict[str, object]] = []

    async def send(message):  # type: ignore[no-untyped-def]
        sent.append(message)

    async def receive():  # type: ignore[no-untyped-def]
        raise AssertionError("不应读取正文")

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/codebook/area-codes/resolve",
        "headers": [(b"content-type", b"multipart/form-data; boundary=x")],
    }
    await middleware(scope, receive, send)
    assert sent[0]["status"] == 401


@pytest.mark.asyncio
async def test_small_request_is_forwarded() -> None:
    middleware = RequestBodyLimitMiddleware(_ok_app, max_bytes=100)
    sent: list[dict[str, object]] = []

    async def send(message):  # type: ignore[no-untyped-def]
        sent.append(message)

    async def receive():  # type: ignore[no-untyped-def]
        return {"type": "http.request", "body": b"abc", "more_body": False}

    scope = {"type": "http", "method": "POST", "path": "/api/v1/auth/login", "headers": [], "seen": b""}
    await middleware(scope, receive, send)
    assert sent[0]["status"] == 200
    assert scope["seen"] == b"abc"
