from __future__ import annotations

import json

import httpx
import pytest

from platform_common.authz import AuthzClient
from platform_common.errors import DependencyUnavailableError, PermissionDeniedError, UnauthenticatedError


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/internal/v1/authorize":
        payload = json.loads(request.content)
        if request.headers.get("x-internal-token") != "secret":
            return httpx.Response(401, json={"code": "INTERNAL_CALLER_REJECTED", "message": "no", "data": None})
        if payload.get("access_token") == "expired":
            return httpx.Response(401, json={"code": "AUTH_UNAUTHENTICATED", "message": "no", "data": None})
        if payload.get("resource") == "down":
            return httpx.Response(503, json={"code": "DEPENDENCY_UNAVAILABLE", "message": "down", "data": None})
        if payload.get("resource") == "deny":
            return httpx.Response(
                200,
                json={"code": "OK", "message": "success", "data": {"allowed": False, "reason": "没有权限"}},
            )
        return httpx.Response(
            200,
            json={
                "code": "OK",
                "message": "success",
                "data": {
                    "allowed": True,
                    "level": "READ",
                    "user": {"id": "u1", "username": "reader"},
                },
            },
        )
    return httpx.Response(404)


@pytest.mark.asyncio
async def test_authz_client_allow_and_deny() -> None:
    client = AuthzClient(
        base_url="http://iam",
        service_name="audit-service",
        service_secret="secret",
        transport=httpx.MockTransport(_handler),
    )
    allowed = await client.authorize(access_token="t", resource="system.users", action="list")
    assert allowed.allowed is True
    assert allowed.username == "reader"
    with pytest.raises(PermissionDeniedError):
        await client.authorize(access_token="t", resource="deny", action="list")
    await client.aclose()


@pytest.mark.asyncio
async def test_authz_client_dependency_failure_is_503() -> None:
    client = AuthzClient(
        base_url="http://iam",
        service_name="audit-service",
        service_secret="secret",
        transport=httpx.MockTransport(_handler),
    )
    with pytest.raises(DependencyUnavailableError):
        await client.authorize(access_token="t", resource="down", action="list")
    await client.aclose()


@pytest.mark.asyncio
async def test_authz_client_bad_secret_is_503_not_unauthenticated() -> None:
    """本服务内部密钥配错是部署问题，不能让前端以为用户掉线、反复刷新会话。"""

    client = AuthzClient(
        base_url="http://iam",
        service_name="audit-service",
        service_secret="wrong",
        transport=httpx.MockTransport(_handler),
    )
    with pytest.raises(DependencyUnavailableError):
        await client.authorize(access_token="t", resource="system.users", action="list")
    await client.aclose()


@pytest.mark.asyncio
async def test_authz_client_expired_user_token_is_401() -> None:
    client = AuthzClient(
        base_url="http://iam",
        service_name="audit-service",
        service_secret="secret",
        transport=httpx.MockTransport(_handler),
    )
    with pytest.raises(UnauthenticatedError):
        await client.authorize(access_token="expired", resource="system.users", action="list")
    await client.aclose()


@pytest.mark.asyncio
async def test_resource_levels_skips_denied_but_never_swallows_outage() -> None:
    """按分类收窄可见范围：没授权的分类不出现；鉴权服务不可用仍是 503，不能当成「没有任何分类」。"""

    from starlette.requests import Request

    from platform_common.service_authz import resource_levels

    client = AuthzClient(
        base_url="http://iam",
        service_name="ai-service",
        service_secret="secret",
        transport=httpx.MockTransport(_handler),
    )
    request = Request({"type": "http", "headers": [(b"authorization", b"Bearer t")]})
    assert await resource_levels(request, client, ["ai.category.policy", "deny"], "list") == {
        "ai.category.policy": "READ"
    }
    with pytest.raises(DependencyUnavailableError):
        await resource_levels(request, client, ["ai.category.policy", "down"], "list")
    await client.aclose()
