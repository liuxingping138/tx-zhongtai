"""限定公司网络的模块：AuthzClient 带上来源 IP，IAM 回 NETWORK_DENIED 时原样抛出（不当成普通的没权限）。"""

from __future__ import annotations

import json
import re
from typing import ClassVar

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from platform_common.actors import Actor
from platform_common.authz import AuthzClient
from platform_common.errors import NetworkDeniedError, PermissionDeniedError, register_exception_handlers
from platform_common.service_authz import build_permission_dependency, resource_levels

seen: list[dict[str, object]] = []


DENIED = {"code": "NETWORK_DENIED", "message": "智库只能在公司网络下访问。你当前的 IP 是 5.6.7.8"}


def _handler(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    seen.append(payload)
    if payload.get("client_ip") == "5.6.7.8":
        return httpx.Response(403, json=DENIED)
    if payload.get("resource") == "nope":
        return httpx.Response(403, json={"code": "AUTH_PERMISSION_DENIED", "message": "没有权限"})
    return httpx.Response(
        200,
        json={"code": "OK", "data": {"allowed": True, "level": "READ", "user": {"id": "u1", "username": "u"}}},
    )


def _client() -> AuthzClient:
    return AuthzClient(
        base_url="http://iam", service_name="t", service_secret="s", transport=httpx.MockTransport(_handler)
    )


@pytest.mark.asyncio
async def test_client_ip_is_sent_only_when_given_and_network_denial_keeps_message() -> None:
    seen.clear()
    client = _client()
    await client.authorize(access_token="t", resource="thinktank.knowledge", action="list")
    assert "client_ip" not in seen[-1]
    with pytest.raises(NetworkDeniedError, match=re.escape("5.6.7.8")):
        await client.authorize(access_token="t", resource="thinktank.knowledge", action="list", client_ip="5.6.7.8")
    with pytest.raises(PermissionDeniedError):
        await client.authorize(access_token="t", resource="nope", action="list", client_ip="1.1.1.1")
    await client.aclose()


def _app(send_client_ip: bool) -> FastAPI:
    client = _client()
    require = build_permission_dependency(lambda: client, send_client_ip=send_client_ip)
    app = FastAPI()
    register_exception_handlers(app)
    # 闭包里的依赖不能写进 Annotated（延迟标注下 FastAPI 解析不了局部变量），用默认值写法
    actor_dep = Depends(require("thinktank.knowledge", "read"))

    @app.get("/x")
    async def route(request_actor: Actor = actor_dep) -> dict[str, str]:
        return {"id": request_actor.id}

    return app


def test_dependency_sends_gateway_ip_and_surfaces_network_denial() -> None:
    seen.clear()
    headers = {"Authorization": "Bearer t", "X-Forwarded-For": "5.6.7.8"}
    res = TestClient(_app(send_client_ip=True)).get("/x", headers=headers)
    assert res.status_code == 403
    assert res.json()["code"] == "NETWORK_DENIED"
    assert seen[-1]["client_ip"] == "5.6.7.8"
    # 没开 send_client_ip 的服务照旧不带
    res = TestClient(_app(send_client_ip=False)).get("/x", headers=headers)
    assert res.status_code == 200
    assert "client_ip" not in seen[-1]


@pytest.mark.asyncio
async def test_scope_lookups_in_the_same_request_also_carry_the_ip() -> None:
    seen.clear()

    class _State:
        authz_client_ip = "1.1.1.1"

    class _Request:
        state = _State()
        headers: ClassVar[dict[str, str]] = {"authorization": "Bearer t"}

    levels = await resource_levels(_Request(), _client(), ["thinktank.file_type.a"], "export")  # type: ignore[arg-type]
    assert levels == {"thinktank.file_type.a": "READ"}
    assert seen[-1]["client_ip"] == "1.1.1.1"
