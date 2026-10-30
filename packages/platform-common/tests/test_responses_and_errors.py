from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from platform_common.errors import NotFoundError, PermissionDeniedError, register_exception_handlers
from platform_common.request_context import RequestIdMiddleware, get_request_id
from platform_common.responses import ok, paginate


def test_ok_response_shape() -> None:
    resp = ok({"foo": "bar"}, request_id="req-1")
    assert resp.code == "OK"
    assert resp.message == "success"
    assert resp.data == {"foo": "bar"}
    assert resp.request_id == "req-1"


def test_paginate_defaults() -> None:
    page = paginate([1, 2, 3], total=3)
    assert page.page == 1
    assert page.page_size == 20
    assert page.items == [1, 2, 3]


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    @app.get("/boom-403")
    async def boom_403() -> None:
        raise PermissionDeniedError()

    @app.get("/boom-404")
    async def boom_404() -> None:
        raise NotFoundError("找不到用户")

    @app.get("/boom-500")
    async def boom_500() -> None:
        raise RuntimeError("unexpected")

    return app


def test_permission_denied_returns_403_with_unified_body() -> None:
    client = TestClient(_build_test_app(), raise_server_exceptions=False)
    resp = client.get("/boom-403")
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "AUTH_PERMISSION_DENIED"
    assert body["data"] is None
    assert "request_id" in body
    assert resp.headers["X-Request-Id"] == body["request_id"]


def test_not_found_returns_404() -> None:
    client = TestClient(_build_test_app(), raise_server_exceptions=False)
    resp = client.get("/boom-404")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == "RESOURCE_NOT_FOUND"
    assert body["message"] == "找不到用户"


def test_unexpected_exception_returns_500_without_leaking_stack() -> None:
    client = TestClient(_build_test_app(), raise_server_exceptions=False)
    resp = client.get("/boom-500")
    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert "unexpected" not in body["message"]


def test_unexpected_exception_keeps_the_request_id(caplog: pytest.LogCaptureFixture) -> None:
    """未捕获异常的 500 由最外层中间件处理，那时请求 ID 中间件已经退出：响应体、响应头、日志都要带上同一个 ID。"""

    client = TestClient(_build_test_app(), raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="platform_common.errors"):
        resp = client.get("/boom-500", headers={"X-Request-Id": "trace-500"})
    assert resp.status_code == 500
    assert resp.json()["request_id"] == "trace-500"
    assert resp.headers["X-Request-Id"] == "trace-500"
    record = next(item for item in caplog.records if item.name == "platform_common.errors")
    assert "trace-500" in record.getMessage()


def test_unexpected_exception_gets_a_generated_request_id() -> None:
    client = TestClient(_build_test_app(), raise_server_exceptions=False)
    resp = client.get("/boom-500")
    generated = resp.json()["request_id"]
    assert generated and len(generated) == 32
    assert resp.headers["X-Request-Id"] == generated


def test_log_lines_written_by_the_500_handler_carry_the_request_id() -> None:
    """结构化日志的 request_id 字段从上下文变量取，处理器写日志时要临时放回去。"""

    seen: list[str | None] = []
    app = _build_test_app()

    class _Probe(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(get_request_id())

    probe = _Probe()
    errors_logger = logging.getLogger("platform_common.errors")
    errors_logger.addHandler(probe)
    try:
        TestClient(app, raise_server_exceptions=False).get("/boom-500", headers={"X-Request-Id": "ctx-500"})
    finally:
        errors_logger.removeHandler(probe)
    assert seen == ["ctx-500"]
    assert get_request_id() is None


def test_request_id_passthrough_from_header() -> None:
    client = TestClient(_build_test_app(), raise_server_exceptions=False)
    resp = client.get("/boom-404", headers={"X-Request-Id": "client-supplied-id"})
    assert resp.headers["X-Request-Id"] == "client-supplied-id"
    assert resp.json()["request_id"] == "client-supplied-id"


@pytest.mark.parametrize("bad", ["x" * 65, "has space", "", "a;b"])
def test_unacceptable_request_id_is_replaced_not_echoed(bad: str) -> None:
    """审计事件的 request_id 最长 64 字：客户端塞个超长或带空格的 ID，审计服务会拒收这次操作的事件。
    不合格的不透传，自己生成一个。"""

    client = TestClient(_build_test_app(), raise_server_exceptions=False)
    resp = client.get("/boom-404", headers={"X-Request-Id": bad})
    generated = resp.headers["X-Request-Id"]
    assert generated != bad and len(generated) == 32 and resp.json()["request_id"] == generated
