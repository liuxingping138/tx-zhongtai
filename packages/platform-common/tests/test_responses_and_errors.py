from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from platform_common.errors import NotFoundError, PermissionDeniedError, register_exception_handlers
from platform_common.request_context import RequestIdMiddleware
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


def test_request_id_passthrough_from_header() -> None:
    client = TestClient(_build_test_app(), raise_server_exceptions=False)
    resp = client.get("/boom-404", headers={"X-Request-Id": "client-supplied-id"})
    assert resp.headers["X-Request-Id"] == "client-supplied-id"
    assert resp.json()["request_id"] == "client-supplied-id"
