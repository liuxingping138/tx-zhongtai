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
from platform_common.errors import UnauthenticatedError

from app.api import auth as auth_api
from app.api import security
from app.api.security import CurrentPrincipal, get_principal
from app.application import auth_service
from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.rate_limit import LoginLockedError
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
        self.reserve = AsyncMock()
        self.succeeded = AsyncMock()
        self.release = AsyncMock()
        self.first_notice = AsyncMock(return_value=True)
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
    _Limiter.instances[0].succeeded.assert_awaited_once()


def test_failed_login_counts_failure_and_writes_audit_in_its_own_session(
    client: TestClient, service: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """登录失败要在独立会话里留痕：请求本身的事务会因异常回滚。"""

    fail_session = _FailSession()
    monkeypatch.setattr(auth_api, "SideSessionLocal", lambda: fail_session)
    service.authenticate_password.side_effect = UnauthenticatedError()
    response = client.post("/api/v1/auth/login", json={"username": "zhangsan", "password": "bad"})
    assert response.status_code == 401
    # 占的名额留着就是一次失败，不退回。
    _Limiter.instances[0].release.assert_not_awaited()
    _Limiter.instances[0].succeeded.assert_not_awaited()
    service.record_login_failure.assert_awaited_once()
    fail_session.commit.assert_awaited_once()


def test_failure_log_that_cannot_get_a_connection_still_answers_401(
    client: TestClient, service: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """留痕用的小连接池正忙（一波错密码登录）：只记日志，这次照样回 401，不变成 500。"""

    class _Busy:
        async def __aenter__(self) -> Any:
            raise TimeoutError("QueuePool limit reached")

        async def __aexit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(auth_api, "SideSessionLocal", _Busy)
    service.authenticate_password.side_effect = UnauthenticatedError()
    response = client.post("/api/v1/auth/login", json={"username": "zhangsan", "password": "bad"})
    assert response.status_code == 401
    _Limiter.instances[0].release.assert_not_awaited()


def test_side_writes_use_their_own_small_pool() -> None:
    """请求还占着一条连接时再要一条的写（留痕、最近活跃）不进请求的连接池：
    共用的话并发十几个就互相等到超时，全平台鉴权一起 503。"""

    from app.application import audit_outbox, auth_service
    from app.core import database

    assert database.side_engine is not database.engine
    assert database.side_engine.pool.timeout() <= 1  # type: ignore[attr-defined]
    assert auth_service.SideSessionLocal is database.SideSessionLocal
    assert audit_outbox.SideSessionLocal is database.SideSessionLocal


def test_attempt_while_locked_is_logged_as_locked(
    client: TestClient, service: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """锁定期间的尝试也进登录日志，账号被锁和出口 IP 被限制分开写；同一窗口里只记第一次，照样拒绝。"""

    monkeypatch.setattr(auth_api, "SideSessionLocal", _FailSession)
    blocked = {"by_ip": False}

    class _Locked(_Limiter):
        def __init__(self, *args: Any) -> None:
            super().__init__(*args)
            self.reserve = AsyncMock(side_effect=LoginLockedError(by_ip=blocked["by_ip"], retry_after_seconds=60))

    monkeypatch.setattr(auth_api, "LoginRateLimiter", _Locked)
    response = client.post("/api/v1/auth/login", json={"username": "zhangsan", "password": "pw"})
    assert response.status_code == 429
    service.authenticate_password.assert_not_awaited()
    assert service.record_login_failure.await_args.kwargs["reason"] == "locked_account"
    blocked["by_ip"] = True
    client.post("/api/v1/auth/login", json={"username": "zhangsan", "password": "pw"})
    assert service.record_login_failure.await_args.kwargs["reason"] == "locked_ip"


def test_locked_attempts_after_the_first_are_not_logged_again(
    client: TestClient, service: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_api, "SideSessionLocal", _FailSession)

    class _Quiet(_Limiter):
        def __init__(self, *args: Any) -> None:
            super().__init__(*args)
            self.reserve = AsyncMock(side_effect=LoginLockedError(by_ip=False, retry_after_seconds=60))
            self.first_notice = AsyncMock(return_value=False)

    monkeypatch.setattr(auth_api, "LoginRateLimiter", _Quiet)
    response = client.post("/api/v1/auth/login", json={"username": "zhangsan", "password": "pw"})
    assert response.status_code == 429
    service.record_login_failure.assert_not_awaited()


def test_unexpected_errors_give_the_try_back(client: TestClient, service: MagicMock) -> None:
    """库出错之类没走到验密码结果，不能算一次失败。"""

    service.authenticate_password.side_effect = RuntimeError("db down")
    with pytest.raises(RuntimeError):
        client.post("/api/v1/auth/login", json={"username": "zhangsan", "password": "pw"})
    _Limiter.instances[-1].release.assert_awaited_once()


def test_disabled_account_failure_has_its_own_reason(
    client: TestClient, service: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_api, "SideSessionLocal", _FailSession)
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


def test_wrong_old_password_counts_as_a_failed_login_and_is_audited(
    client: TestClient, service: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """拿到别人令牌的人原来能无限次试原密码：现在和登录共用失败计数（占的名额不退回），每次留审计。"""

    audited: list[dict[str, Any]] = []

    async def enqueue(**kwargs: Any) -> None:
        audited.append(kwargs)

    monkeypatch.setattr(auth_api, "enqueue_independent", enqueue)
    service.change_password.side_effect = auth_service.WrongOldPasswordError()
    _signed_in()
    response = client.put("/api/v1/auth/password", json={"old_password": "x", "new_password": "y"})
    assert response.status_code == 422
    limiter = _Limiter.instances[0]
    limiter.reserve.assert_awaited_once()
    limiter.release.assert_not_awaited()
    assert audited[0]["event_type"] == "auth.password.change_failed"
    assert audited[0]["payload"]["reason"] == "wrong_old_password"


def test_missing_bearer_token_is_unauthenticated(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.asyncio
async def test_token_without_session_claim_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "decode_access_token", lambda *_: {"sub": str(uuid.uuid4())})
    with pytest.raises(UnauthenticatedError):
        await security.principal_from_access_token("token", MagicMock(), SETTINGS)


@pytest.mark.asyncio
async def test_every_token_request_counts_as_activity(monkeypatch: pytest.MonkeyPatch) -> None:
    """带令牌的请求（IAM 自己的接口、业务服务的 authorize）都记一次活跃，在线用户据此看 30 分钟内有没有操作。"""

    row = SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr(security, "decode_access_token", lambda *_: {"sub": str(USER.id), "sid": str(row.id)})
    monkeypatch.setattr(security.auth_service, "load_principal", AsyncMock(return_value=(USER, row)))
    noted = AsyncMock()
    monkeypatch.setattr(security.auth_service, "note_activity", noted)
    principal = await security.principal_from_access_token("token", MagicMock(), SETTINGS)
    assert principal.session is row
    noted.assert_awaited_once_with(row, every_seconds=SETTINGS.session_touch_seconds)


def test_production_requires_origin_header() -> None:
    request = SimpleNamespace(headers={})
    production = SETTINGS.model_copy(update={"environment": Environment.PRODUCTION})
    with pytest.raises(Exception, match="缺少 Origin"):
        security.check_origin(request, production)  # type: ignore[arg-type]  # 只用到 headers 的替身
    security.check_origin(request, SETTINGS)  # type: ignore[arg-type]  # 只用到 headers 的替身
