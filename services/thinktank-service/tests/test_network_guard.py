"""智库网络准入：公司 IP、白名单（含网段、到期）、关掉限制，以及挂在哪些路由上。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from platform_common.actors import Actor
from platform_common.errors import ApiError
from platform_common.route_audit import iter_api_routes

from app.access.api.guard import require_trusted_network
from app.access.application import gate
from app.access.application import whitelist as service
from app.access.domain.networks import InvalidNetworkError, normalize_network, parse_address, range_contains
from app.access.repositories import whitelist as repo
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.main import app

NOW = datetime(2026, 11, 27, 8, 0, tzinfo=UTC)
ACTOR = Actor(id="admin", name="管理员")


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"network_guard_enabled": True, "office_networks": "1.119.196.74"}
    values.update(overrides)
    return Settings(**values)


def _guarded_settings() -> Settings:
    """依赖覆盖用：不能带 **kwargs，FastAPI 会把它当成查询参数。"""

    return _settings()


def _stub_ranges(monkeypatch: pytest.MonkeyPatch, rows: list[tuple[str, datetime]]) -> AsyncMock:
    mock = AsyncMock(return_value=rows)
    monkeypatch.setattr(repo, "active_ranges", mock)
    return mock


# ---------- 地址规则 ----------


def test_normalize_network_accepts_ip_and_narrow_ranges() -> None:
    assert normalize_network(" 1.2.3.4 ") == "1.2.3.4"
    assert normalize_network("1.2.3.4/32") == "1.2.3.4"
    assert normalize_network("1.2.3.9/24") == "1.2.3.0/24"
    assert normalize_network("2001:db8::1") == "2001:db8::1"


@pytest.mark.parametrize("raw", ["", "abc", "1.2.3.256", "1.2.0.0/16", "0.0.0.0/0", "2001:db8::/32"])
def test_normalize_network_rejects_bad_or_too_wide(raw: str) -> None:
    with pytest.raises(InvalidNetworkError):
        normalize_network(raw)


def test_parse_address_unwraps_ipv4_mapped_and_rejects_garbage() -> None:
    assert str(parse_address("::ffff:1.119.196.74")) == "1.119.196.74"
    assert parse_address("testclient") is None
    addr = parse_address("10.0.0.8")
    assert addr is not None
    assert range_contains("10.0.0.0/24", addr) is True
    assert range_contains("10.0.1.0/24", addr) is False
    assert range_contains("not-an-ip", addr) is False


def test_settings_reject_bad_office_network() -> None:
    with pytest.raises(ValueError, match="OFFICE_NETWORKS"):
        _settings(office_networks="1.119.196.74,bad")
    with pytest.raises(ValueError, match="为空"):
        _settings(office_networks=" ")
    assert _settings(office_networks="1.119.196.74, 2.2.2.0/24").office_network_items() == [
        "1.119.196.74",
        "2.2.2.0/24",
    ]


# ---------- 判定 ----------


async def test_office_ip_is_allowed_without_touching_database(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = _stub_ranges(monkeypatch, [])
    decision = await gate.decide(AsyncMock(), _settings(), "1.119.196.74", now=NOW)
    assert (decision.allowed, decision.via) == (True, "office")
    mock.assert_not_awaited()


async def test_whitelisted_ip_is_allowed_with_latest_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    later = NOW + timedelta(days=3)
    _stub_ranges(monkeypatch, [("8.8.8.0/24", NOW + timedelta(days=1)), ("8.8.8.8", later), ("9.9.9.9", later)])
    decision = await gate.decide(AsyncMock(), _settings(), "8.8.8.8", now=NOW)
    assert (decision.allowed, decision.via, decision.expires_at) == (True, "whitelist", later)


async def test_other_ip_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_ranges(monkeypatch, [("9.9.9.9", NOW + timedelta(days=1))])
    decision = await gate.decide(AsyncMock(), _settings(), "8.8.8.8", now=NOW)
    assert decision.allowed is False
    assert (await gate.decide(AsyncMock(), _settings(), "testclient", now=NOW)).allowed is False


async def test_guard_disabled_allows_everyone(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = _stub_ranges(monkeypatch, [])
    decision = await gate.decide(AsyncMock(), _settings(network_guard_enabled=False), "8.8.8.8", now=NOW)
    assert (decision.allowed, decision.via) == (True, "disabled")
    mock.assert_not_awaited()


# ---------- 挂载与 HTTP ----------


def test_guard_covers_every_business_route_but_not_whitelist_admin() -> None:
    for route in iter_api_routes(app):
        calls = {dep.call for dep in route.dependant.dependencies}
        guarded = require_trusted_network in calls
        if route.path.startswith("/api/v1/thinktank/ip-whitelist"):
            assert not guarded, route.path
        elif route.path.startswith("/api/v1/thinktank/"):
            assert guarded, route.path


@pytest.fixture
def guarded_client(monkeypatch: pytest.MonkeyPatch) -> Any:
    async def _db() -> Any:
        yield AsyncMock()

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_settings] = _guarded_settings
    _stub_ranges(monkeypatch, [("8.8.8.8", datetime.now(UTC) + timedelta(hours=1))])
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_denied_request_gets_403_with_code_and_ip(guarded_client: TestClient) -> None:
    res = guarded_client.get("/api/v1/thinktank/favorites", headers={"X-Forwarded-For": "5.6.7.8"})
    assert res.status_code == 403
    body = res.json()
    assert body["code"] == gate.NETWORK_DENIED_CODE
    assert "5.6.7.8" in body["message"]


def test_allowed_request_passes_guard_and_reaches_auth(guarded_client: TestClient) -> None:
    # 过了网络准入，接着是登录校验：没带令牌回 401，说明没被网络拦下。
    for ip in ("1.119.196.74", "8.8.8.8"):
        res = guarded_client.get("/api/v1/thinktank/favorites", headers={"X-Forwarded-For": ip})
        assert res.status_code == 401, ip


# ---------- 白名单维护 ----------


class _Session:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


def _input(**overrides: Any) -> service.WhitelistInput:
    values: dict[str, Any] = {
        "ip_range": "8.8.8.8",
        "holder": "张三",
        "reason": "出差",
        "expires_at": datetime.now(UTC) + timedelta(days=7),
    }
    values.update(overrides)
    return service.WhitelistInput(**values)


@pytest.fixture
def audit(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(service, "enqueue_event", mock)
    monkeypatch.setattr(repo, "find_active_same_range", AsyncMock(return_value=None))
    return mock


async def test_create_entry_normalizes_and_audits(audit: AsyncMock) -> None:
    session = _Session()
    out = await service.create_entry(
        session,  # type: ignore[arg-type]
        _settings(),
        actor=ACTOR,
        data=_input(ip_range="8.8.8.9/24", holder=" 张三 "),
    )
    assert (out["ip_range"], out["holder"], out["active"]) == ("8.8.8.0/24", "张三", True)
    assert session.added[0].created_by_name == "管理员"
    assert audit.await_args.kwargs["event_type"] == "thinktank.ip_whitelist.created"


async def test_naive_expiry_is_read_as_beijing_time(audit: AsyncMock) -> None:
    naive = (datetime.now(UTC) + timedelta(days=2)).replace(tzinfo=None)
    session = _Session()
    await service.create_entry(session, _settings(), actor=ACTOR, data=_input(expires_at=naive))  # type: ignore[arg-type]
    assert session.added[0].expires_at.utcoffset() == timedelta(hours=8)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"expires_at": datetime.now(UTC) - timedelta(minutes=1)}, "晚于现在"),
        ({"expires_at": datetime.now(UTC) + timedelta(days=400)}, "最多开通"),
        ({"ip_range": "1.2.0.0/16"}, "/24"),
        ({"holder": "  "}, "使用人"),
    ],
)
async def test_create_entry_rejects_bad_input(audit: AsyncMock, overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ApiError, match=message) as info:
        await service.create_entry(_Session(), _settings(), actor=ACTOR, data=_input(**overrides))  # type: ignore[arg-type]
    assert info.value.http_status == 422
    audit.assert_not_awaited()


async def test_create_entry_rejects_active_duplicate(monkeypatch: pytest.MonkeyPatch, audit: AsyncMock) -> None:
    existing = type("E", (), {"holder": "李四", "expires_at": NOW})()
    monkeypatch.setattr(repo, "find_active_same_range", AsyncMock(return_value=existing))
    with pytest.raises(ApiError, match="李四") as info:
        await service.create_entry(_Session(), _settings(), actor=ACTOR, data=_input())  # type: ignore[arg-type]
    assert info.value.http_status == 409


async def test_update_and_delete_missing_entry_is_404(monkeypatch: pytest.MonkeyPatch, audit: AsyncMock) -> None:
    monkeypatch.setattr(repo, "get_entry", AsyncMock(return_value=None))
    with pytest.raises(ApiError) as info:
        await service.update_entry(
            _Session(),  # type: ignore[arg-type]
            _settings(),
            actor=ACTOR,
            entry_id=uuid.uuid4(),
            data=_input(),
        )
    assert info.value.http_status == 404
    with pytest.raises(ApiError):
        await service.delete_entry(_Session(), actor=ACTOR, entry_id=uuid.uuid4())  # type: ignore[arg-type]
