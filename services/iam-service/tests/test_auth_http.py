"""认证接口的 HTTP 行为：Cookie、CSRF/Origin 校验、登录失败留痕，以及会话依赖覆盖后路由仍按预期提交。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from platform_common.config import Environment
from platform_common.errors import RateLimitedError, UnauthenticatedError

from app.api import auth as auth_api
from app.api import security
from app.api.security import CurrentPrincipal, get_principal
from app.core.config import get_settings
from app.core.database import get_db_session
from app.main import app

SETTINGS = get_settings()
CSRF = "csrf-fixture"
USER = SimpleNamespace(
    id=uuid.uuid4(),
    username="zhangsan",
    display_name="张三",
    must_change_password=False,
    status="active",
)


class _Limiter:
    instances: ClassVar[list[_Limiter]] = []

    def __init__(self, *_: Any) -> None:
        self.assert_allowed = AsyncMock()
        self.clear = AsyncMock()
        self.record_failure = AsyncMock()
        _Limiter.instances.append(self)


class _FailSession:
    def __init__(self) -> None:
        self.commit = AsyncMock()

    async def __aenter__(self) -> _FailSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    fake.authenticate_password = AsyncMock(return_value=USER)
    fake.login_success = AsyncMock(return_value=("access-1", "refresh-1", object()))
    fake.record_login_failure = AsyncMock()
    fake.refresh = AsyncMock(return_value=("access-2", None, object(), USER))
    fake.logout = AsyncMock()
    fake.logout_all = AsyncMock(return_value=3)
    fake.change_password = AsyncMock(return_value=("access-3", "refresh-3", object()))
    monkeypatch.setattr(auth_api, "AuthService", lambda *_: fake)
    monkeypatch.setattr(auth_api, "LoginRateLimiter", _Limiter)
    _Limiter.instances.clear()
    return fake


@pytest.fixture
def client(service: MagicMock) -> Iterator[TestClient]:
    async def _session() -> AsyncIterator[MagicMock]:
        yield MagicMock()

    app.dependency_overrides[get_db_session] = _session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _signed_in(user: Any = USER) -> CurrentPrincipal:
    principal = CurrentPrincipal(user=user, session=SimpleNamespace(id=uuid.uuid4()), claims={})
    app.dependency_overrides[get_principal] = lambda: principal
    return principal


def _with_csrf(client: TestClient) -> dict[str, str]:
    client.cookies.set(SETTINGS.csrf_cookie_name, CSRF)
    return {SETTINGS.csrf_header_name: CSRF}


def test_csrf_endpoint_returns_token_and_sets_readable_cookie(client: TestClient) -> None:
    response = client.get("/api/v1/auth/csrf")
    token = response.json()["data"]["csrf_token"]
    assert response.cookies[SETTINGS.csrf_cookie_name] == token
    assert "httponly" not in response.headers["set-cookie"].lower()


def test_login_sets_refresh_cookie_and_clears_rate_limit(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "zhangsan", "password": "pw"})
    assert response.status_code == 200
    assert response.json()["data"]["access_token"] == "access-1"
    assert response.cookies[SETTINGS.refresh_cookie_name] == "refresh-1"
    _Limiter.instances[0].clear.assert_awaited_once()


def test_failed_login_counts_failure_and_writes_audit_in_its_own_session(
    client: TestClient, service: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """登录失败要在独立会话里留痕：请求本身的事务会因异常回滚。"""

    fail_session = _FailSession()
    monkeypatch.setattr(auth_api, "SessionLocal", lambda: fail_session)
    service.authenticate_password.side_effect = UnauthenticatedError()
    response = client.post("/api/v1/auth/login", json={"username": "zhangsan", "password": "bad"})
    assert response.status_code == 401
    _Limiter.instances[0].record_failure.assert_awaited_once()
    service.record_login_failure.assert_awaited_once()
    fail_session.commit.assert_awaited_once()


def test_attempt_while_locked_is_logged_as_locked(
    client: TestClient, service: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """锁定期间的尝试也进登录日志，原因是 locked，并且照样拒绝。"""

    monkeypatch.setattr(auth_api, "SessionLocal", _FailSession)

    class _Locked(_Limiter):
        def __init__(self, *args: Any) -> None:
            super().__init__(*args)
            self.assert_allowed = AsyncMock(side_effect=RateLimitedError("登录失败次数过多，请稍后重试"))

    monkeypatch.setattr(auth_api, "LoginRateLimiter", _Locked)
    response = client.post("/api/v1/auth/login", json={"username": "zhangsan", "password": "pw"})
    assert response.status_code == 429
    service.authenticate_password.assert_not_awaited()
    assert service.record_login_failure.await_args.kwargs["reason"] == "locked"


def test_disabled_account_failure_has_its_own_reason(
    client: TestClient, service: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_api, "SessionLocal", _FailSession)
    service.authenticate_password.side_effect = UnauthenticatedError("账号不可用")
    client.post("/api/v1/auth/login", json={"username": "zhangsan", "password": "pw"})
    assert service.record_login_failure.await_args.kwargs["reason"] == "disabled"


def test_refresh_requires_matching_csrf(client: TestClient) -> None:
    client.cookies.set(SETTINGS.csrf_cookie_name, CSRF)
    response = client.post("/api/v1/auth/refresh", headers={SETTINGS.csrf_header_name: "other"})
    assert response.status_code == 403


def test_refresh_without_cookie_is_unauthenticated(client: TestClient) -> None:
    assert client.post("/api/v1/auth/refresh", headers=_with_csrf(client)).status_code == 401


def test_refresh_rejects_foreign_origin(client: TestClient) -> None:
    headers = {**_with_csrf(client), "origin": "https://evil.example"}
    assert client.post("/api/v1/auth/refresh", headers=headers).status_code == 403


def test_refresh_keeps_cookie_when_token_not_rotated(client: TestClient) -> None:
    headers = _with_csrf(client)
    client.cookies.set(SETTINGS.refresh_cookie_name, "refresh-old")
    response = client.post("/api/v1/auth/refresh", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["access_token"] == "access-2"
    assert SETTINGS.refresh_cookie_name not in response.cookies


def test_refresh_rotates_cookie(client: TestClient, service: MagicMock) -> None:
    service.refresh.return_value = ("access-2", "refresh-new", object(), USER)
    headers = _with_csrf(client)
    client.cookies.set(SETTINGS.refresh_cookie_name, "refresh-old")
    response = client.post("/api/v1/auth/refresh", headers=headers)
    assert response.cookies[SETTINGS.refresh_cookie_name] == "refresh-new"


def test_logout_revokes_current_session_and_clears_cookies(client: TestClient, service: MagicMock) -> None:
    principal = _signed_in()
    response = client.post("/api/v1/auth/logout", headers=_with_csrf(client))
    assert response.status_code == 204
    service.logout.assert_awaited_once()
    assert service.logout.await_args.args == (principal.session,)
    assert service.logout.await_args.kwargs["actor_name"] == USER.display_name
    cleared = response.headers.get_list("set-cookie")
    assert any(item.startswith(f"{SETTINGS.refresh_cookie_name}=") and "Max-Age=0" in item for item in cleared)


def test_logout_all_reports_revoked_count(client: TestClient) -> None:
    _signed_in()
    response = client.post("/api/v1/auth/logout-all", headers=_with_csrf(client))
    assert response.json()["data"] == {"revoked": 3}


def test_me_returns_identity_and_roles(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _signed_in()
    monkeypatch.setattr(auth_api.auth_service, "role_summary", AsyncMock(return_value=(True, ["超级管理员"])))
    data = client.get("/api/v1/auth/me").json()["data"]
    assert (data["username"], data["is_superadmin"], data["roles"]) == ("zhangsan", True, ["超级管理员"])


def test_permissions_require_password_already_changed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_api, "visible_permissions", AsyncMock(return_value={"items": []}))
    _signed_in()
    assert client.get("/api/v1/auth/permissions").status_code == 200
    _signed_in(SimpleNamespace(**{**vars(USER), "must_change_password": True}))
    assert client.get("/api/v1/auth/permissions").status_code == 403


def test_change_password_issues_new_tokens(client: TestClient) -> None:
    _signed_in()
    response = client.put("/api/v1/auth/password", json={"old_password": "a", "new_password": "b"})
    assert response.json()["data"]["must_change_password"] is False
    assert response.cookies[SETTINGS.refresh_cookie_name] == "refresh-3"


def test_missing_bearer_token_is_unauthenticated(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.asyncio
async def test_token_without_session_claim_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "decode_access_token", lambda *_: {"sub": str(uuid.uuid4())})
    with pytest.raises(UnauthenticatedError):
        await security.principal_from_access_token("token", MagicMock(), SETTINGS)


def test_production_requires_origin_header() -> None:
    request = SimpleNamespace(headers={})
    production = SETTINGS.model_copy(update={"environment": Environment.PRODUCTION})
    with pytest.raises(Exception, match="缺少 Origin"):
        security.check_origin(request, production)  # type: ignore[arg-type]  # 只用到 headers 的替身
    security.check_origin(request, SETTINGS)  # type: ignore[arg-type]  # 只用到 headers 的替身
