"""访问白名单：IAM 鉴权时按来源 IP 核对公司网络和这个人的白名单；管理员维护白名单的校验。"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.errors import ApiError, NetworkDeniedError

from app.application import ip_whitelist as service
from app.application import network_access
from app.core.config import Settings
from app.domain.catalog import ACTION_SPECS, MENU_SPECS, RESOURCE_SPECS, RETIRED_RESOURCE_CODES
from app.domain.enums import GrantLevel, UserStatus
from app.domain.networks import InvalidNetworkError, normalize_network, parse_address

NOW = datetime(2026, 11, 27, 8, 0, tzinfo=UTC)
USER_ID = uuid.uuid4()


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "postgresql+asyncpg://x:y@localhost/db",
        "redis_url": "redis://localhost",
        "network_guard_enabled": True,
        "office_networks": "1.119.196.74",
    }
    values.update(overrides)
    return Settings(**values)


def _ranges(monkeypatch: pytest.MonkeyPatch, rows: list[tuple[str, datetime]]) -> AsyncMock:
    mock = AsyncMock(return_value=rows)
    monkeypatch.setattr(network_access.repo, "active_ranges_for_user", mock)
    return mock


# ---------- 目录 ----------


def test_whitelist_lives_in_system_management_and_old_thinktank_entry_is_retired() -> None:
    by_code = {spec.code: spec for spec in RESOURCE_SPECS}
    assert (by_code["system.ip_whitelist"].name, by_code["system.ip_whitelist"].parent_code) == ("访问白名单", "system")
    assert "thinktank.ip_whitelist" not in by_code
    assert "thinktank.ip_whitelist" in RETIRED_RESOURCE_CODES
    levels = {s.action_code: s.required_level for s in ACTION_SPECS if s.resource_code == "system.ip_whitelist"}
    assert levels == {
        "list": GrantLevel.READ,
        "create": GrantLevel.FULL,
        "update": GrantLevel.FULL,
        "delete": GrantLevel.FULL,
    }
    menu = next(m for m in MENU_SPECS if m.code == "menu.system.ip_whitelist")
    assert (menu.route_name, menu.parent_code, menu.resource_code) == (
        "system-ip-whitelist",
        "menu.system",
        "system.ip_whitelist",
    )


# ---------- 地址 ----------


def test_normalize_network() -> None:
    assert normalize_network(" 1.2.3.4 ") == "1.2.3.4"
    assert normalize_network("1.2.3.9/24") == "1.2.3.0/24"
    for bad in ("", "abc", "1.2.0.0/16", "0.0.0.0/0"):
        with pytest.raises(InvalidNetworkError):
            normalize_network(bad)
    assert str(parse_address("::ffff:1.119.196.74")) == "1.119.196.74"
    assert parse_address(None) is None


def test_settings_reject_bad_office_network() -> None:
    with pytest.raises(ValueError, match="OFFICE_NETWORKS"):
        _settings(office_networks="1.119.196.74,bad")
    with pytest.raises(ValueError, match="为空"):
        _settings(office_networks=" ")


# ---------- 判定 ----------


async def test_only_restricted_resources_are_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = _ranges(monkeypatch, [])
    settings = _settings()
    # 政策等不限定网络的模块：任何 IP 都不查
    await network_access.assert_network_allowed(AsyncMock(), settings, USER_ID, "policy.sources", "8.8.8.8")
    # 公司网络：直接放行、不查库
    await network_access.assert_network_allowed(AsyncMock(), settings, USER_ID, "thinktank.knowledge", "1.119.196.74")
    mock.assert_not_awaited()


async def test_whitelist_is_per_user_and_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    later = NOW + timedelta(hours=2)
    mock = _ranges(monkeypatch, [("8.8.8.8", later), ("9.9.9.0/24", NOW + timedelta(hours=1))])
    decision = await network_access.decide(AsyncMock(), _settings(), USER_ID, "8.8.8.8", now=NOW)
    assert (decision.allowed, decision.via, decision.expires_at) == (True, "whitelist", later)
    assert mock.await_args.args[1] == USER_ID  # 只查这个人自己的白名单
    assert (await network_access.decide(AsyncMock(), _settings(), USER_ID, "9.9.9.200", now=NOW)).allowed is True
    assert (await network_access.decide(AsyncMock(), _settings(), USER_ID, "7.7.7.7", now=NOW)).allowed is False


async def test_denied_message_names_module_and_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    _ranges(monkeypatch, [])
    with pytest.raises(NetworkDeniedError, match=re.escape("智库只能在公司网络下访问。你当前的 IP 是 5.6.7.8")):
        await network_access.assert_network_allowed(AsyncMock(), _settings(), USER_ID, "thinktank.reports", "5.6.7.8")
    # 业务服务没带 IP：按拒绝处理，不能因为少传一个字段就绕过
    with pytest.raises(NetworkDeniedError, match="没能识别"):
        await network_access.assert_network_allowed(AsyncMock(), _settings(), USER_ID, "thinktank.reports", None)


async def test_guard_disabled_skips_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = _ranges(monkeypatch, [])
    settings = _settings(network_guard_enabled=False)
    await network_access.assert_network_allowed(AsyncMock(), settings, USER_ID, "thinktank.knowledge", None)
    mock.assert_not_awaited()


def test_restricted_module_names() -> None:
    assert network_access.restricted_module_names(_settings()) == ["智库"]


# ---------- 维护 ----------


class _Session:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


ACTOR = SimpleNamespace(id=uuid.uuid4(), display_name="管理员")
TARGET = SimpleNamespace(id=USER_ID, username="zhangsan", display_name="张三", status=UserStatus.ACTIVE)


def _input(**overrides: Any) -> service.WhitelistInput:
    values: dict[str, Any] = {
        "user_id": USER_ID,
        "ip_range": "8.8.8.8",
        "reason": "出差",
        "expires_at": datetime.now(UTC) + timedelta(hours=2),
    }
    values.update(overrides)
    return service.WhitelistInput(**values)


@pytest.fixture
def audit(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(service.outbox_repo, "enqueue", mock)
    monkeypatch.setattr(service.repo, "find_active_duplicate", AsyncMock(return_value=None))
    monkeypatch.setattr(service.user_repo, "get_user_by_id", AsyncMock(return_value=TARGET))
    return mock


async def test_create_two_hour_entry_for_a_user(audit: AsyncMock) -> None:
    session = _Session()
    out = await service.create_entry(session, _settings(), actor=ACTOR, data=_input(ip_range="8.8.8.9/24"))  # type: ignore[arg-type]
    assert (out["ip_range"], out["user"]["display_name"], out["active"]) == ("8.8.8.0/24", "张三", True)
    assert session.added[0].user_id == USER_ID
    assert audit.await_args.kwargs["event_type"] == "iam.ip_whitelist.created"
    assert audit.await_args.kwargs["payload"]["username"] == "zhangsan"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"expires_at": datetime.now(UTC) + timedelta(minutes=5)}, "10 分钟"),
        ({"expires_at": datetime.now(UTC) + timedelta(days=400)}, "最多开通"),
        ({"ip_range": "1.2.0.0/16"}, "/24"),
    ],
)
async def test_create_rejects_bad_input(audit: AsyncMock, overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ApiError, match=message) as info:
        await service.create_entry(_Session(), _settings(), actor=ACTOR, data=_input(**overrides))  # type: ignore[arg-type]
    assert info.value.http_status == 422
    audit.assert_not_awaited()


async def test_create_rejects_deleted_user(monkeypatch: pytest.MonkeyPatch, audit: AsyncMock) -> None:
    gone = SimpleNamespace(**{**TARGET.__dict__, "status": UserStatus.DELETED})
    monkeypatch.setattr(service.user_repo, "get_user_by_id", AsyncMock(return_value=gone))
    with pytest.raises(ApiError, match="已删除"):
        await service.create_entry(_Session(), _settings(), actor=ACTOR, data=_input())  # type: ignore[arg-type]


async def test_create_rejects_active_duplicate(monkeypatch: pytest.MonkeyPatch, audit: AsyncMock) -> None:
    existing = SimpleNamespace(expires_at=NOW)
    monkeypatch.setattr(service.repo, "find_active_duplicate", AsyncMock(return_value=existing))
    with pytest.raises(ApiError, match="张三") as info:
        await service.create_entry(_Session(), _settings(), actor=ACTOR, data=_input())  # type: ignore[arg-type]
    assert info.value.http_status == 409


async def test_missing_entry_is_404(monkeypatch: pytest.MonkeyPatch, audit: AsyncMock) -> None:
    monkeypatch.setattr(service.repo, "get_entry", AsyncMock(return_value=None))
    with pytest.raises(ApiError) as info:
        await service.delete_entry(_Session(), actor=ACTOR, entry_id=uuid.uuid4())  # type: ignore[arg-type]
    assert info.value.http_status == 404
