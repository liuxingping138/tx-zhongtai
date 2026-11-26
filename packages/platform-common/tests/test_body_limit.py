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


def _stream_app(limit: int, path_limits: dict[str, int] | None = None):  # type: ignore[no-untyped-def]
    from fastapi import Depends, FastAPI, HTTPException

    from platform_common.errors import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    seen: list[int] = []

    def need_login() -> None:
        raise HTTPException(status_code=401, detail="未认证")

    @app.post("/api/v1/ai/stream/ask")
    async def ask(body: dict[str, object], _: None = Depends(need_login)) -> dict[str, int]:  # pragma: no cover
        seen.append(len(str(body)))
        return {"ok": 1}

    @app.post("/api/v1/other")
    async def other(body: dict[str, object]) -> dict[str, int]:
        return {"size": len(str(body))}

    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=limit, path_limits=path_limits)
    return app


def test_chunked_body_without_content_length_gets_413_before_auth_runs() -> None:
    """分块上传不带 Content-Length：原来整段读进内存才跑鉴权（未登录也一样），几路大正文就能把服务内存打满。"""

    from fastapi.testclient import TestClient

    client = TestClient(_stream_app(1000))

    def chunks():  # type: ignore[no-untyped-def]
        yield b'{"content": "'
        for _ in range(50):
            yield b"x" * 1000
        yield b'"}'

    response = client.post("/api/v1/ai/stream/ask", content=chunks(), headers={"content-type": "application/json"})
    assert response.status_code == 413
    assert response.json()["message"] == "请求体过大"


@pytest.mark.asyncio
async def test_reading_stops_as_soon_as_the_limit_is_passed() -> None:
    pulled = 0

    async def receive():  # type: ignore[no-untyped-def]
        nonlocal pulled
        pulled += 1
        return {"type": "http.request", "body": b"x" * 100, "more_body": pulled < 1000}

    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        while (await receive()).get("more_body"):
            pass

    sent: list[dict[str, object]] = []

    async def send(message):  # type: ignore[no-untyped-def]
        sent.append(message)

    middleware = RequestBodyLimitMiddleware(app, max_bytes=1000)
    await middleware({"type": "http", "method": "POST", "path": "/x", "headers": []}, receive, send)
    assert pulled == 11  # 第 11 块超过 1000 字节就停，不会读完 1000 块
    assert sent[0]["status"] == 413


def test_a_path_prefix_can_have_a_smaller_limit() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(_stream_app(10_000, {"/api/v1/ai/stream": 100}))
    big = {"content": "x" * 500}
    assert client.post("/api/v1/ai/stream/ask", json=big).status_code == 413
    assert client.post("/api/v1/other", json=big).status_code == 200


def test_body_limit_preserves_request_id_and_allows_excel_upload() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from platform_common.request_context import RequestIdMiddleware

    app = FastAPI()

    @app.post("/api/v1/users/files/excel")
    async def upload() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/other")
    async def other() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=100,
        path_limits={"/api/v1/users/files/excel": 5000},
    )
    app.add_middleware(RequestIdMiddleware)
    client = TestClient(app)

    res_401 = client.post(
        "/api/v1/users/files/excel",
        files={"file": ("users.xlsx", b"x" * 400, "application/octet-stream")},
        headers={"x-request-id": "req-upload-401"},
    )
    assert res_401.status_code == 401
    assert res_401.headers.get("x-request-id") == "req-upload-401"
    assert res_401.json()["request_id"] == "req-upload-401"

    res_413 = client.post(
        "/api/v1/other",
        content=b"x" * 200,
        headers={"content-type": "application/json", "x-request-id": "req-limit-1"},
    )
    assert res_413.status_code == 413
    assert res_413.headers.get("x-request-id") == "req-limit-1"
    assert res_413.json()["request_id"] == "req-limit-1"

    res_upload = client.post(
        "/api/v1/users/files/excel",
        files={"file": ("users.xlsx", b"x" * 400, "application/octet-stream")},
        headers={"authorization": "Bearer test-token"},
    )
    assert res_upload.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/thinktank/knowledge/upload",
        "/api/v1/thinktank/knowledge/upload-tags",
        "/api/v1/ai/batch-runs/input-preview",
        "/api/v1/ai/batch-runs",
    ],
)
async def test_new_upload_paths_require_bearer_before_reading(path: str) -> None:
    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        raise AssertionError("未认证上传不应进入应用")

    middleware = RequestBodyLimitMiddleware(app, max_bytes=1024, upload_paths=("/api/v1/ai/batch-runs",))
    sent: list[dict[str, object]] = []

    async def send(message):  # type: ignore[no-untyped-def]
        sent.append(message)

    async def receive():  # type: ignore[no-untyped-def]
        raise AssertionError("不应读取正文")

    scope = {"type": "http", "method": "POST", "path": path, "headers": []}
    await middleware(scope, receive, send)
    assert sent[0]["status"] == 401


def test_longest_prefix_exact_and_suffix_limits_with_small_default() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.post("/api/v1/thinktank/knowledge/upload")
    async def upload() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/thinktank/knowledge/upload-tags")
    async def upload_tags() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/ai/batch-runs")
    async def start_run() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/ai/batch-runs/from-rows")
    async def from_rows() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/ai/prompts/p1/files/excel")
    async def prompt_excel() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/ai/prompts/p1/test-data")
    async def prompt_test_data() -> dict[str, bool]:
        return {"ok": True}

    # 故意把短前缀 /upload 放在长前缀 /upload-tags 前面，验证仍按最长路径前缀和段边界匹配。
    app.add_middleware(
        RequestBodyLimitMiddleware,
        max_bytes=100,
        path_limits={
            "/api/v1/thinktank/knowledge/upload": 1000,
            "/api/v1/thinktank/knowledge/upload-tags": 300,
        },
        exact_limits={"/api/v1/ai/batch-runs": 1000},
        suffix_limits={"/files/excel": 1000},
        upload_paths=("/api/v1/ai/batch-runs",),
    )
    client = TestClient(app, headers={"authorization": "Bearer ok"})

    assert client.post("/api/v1/thinktank/knowledge/upload", content=b"a" * 500).status_code == 200
    assert client.post("/api/v1/thinktank/knowledge/upload-tags", content=b"a" * 200).status_code == 200
    assert client.post("/api/v1/thinktank/knowledge/upload-tags", content=b"a" * 500).status_code == 413
    assert client.post("/api/v1/ai/batch-runs", content=b"a" * 500).status_code == 200
    assert client.post("/api/v1/ai/batch-runs/from-rows", content=b"a" * 200).status_code == 413
    assert client.post("/api/v1/ai/prompts/p1/files/excel", content=b"a" * 500).status_code == 200
    assert client.post("/api/v1/ai/prompts/p1/test-data", content=b"a" * 200).status_code == 413
