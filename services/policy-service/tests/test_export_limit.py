"""导出行数上限的回归测试。"""

from __future__ import annotations

import asyncio
import os

import pytest

# 与 test_route_security_class.py 一致：导入 app 模块前必须先给出数据库配置。
os.environ.setdefault("POLICY_DATABASE_URL", "postgresql+asyncpg://policy_app:test@localhost:5432/policy_db")

from platform_common.errors import ApiError

from app.application import base_tags, interpretations, sources
from app.core.config import get_settings


class _FakeActor:
    id = "u1"
    name = "测试"


@pytest.mark.parametrize(
    ("module", "export_fn"),
    [
        (sources, "export_sources"),
        (base_tags, "export_base_tags"),
        (interpretations, "export_interpretations"),
    ],
)
def test_export_rejects_when_over_limit(monkeypatch: pytest.MonkeyPatch, module, export_fn: str) -> None:
    limit = get_settings().export_max_rows

    async def fake_count(_session: object) -> int:
        return limit + 1

    def fail_list_all(_session: object) -> None:  # pragma: no cover - 不应被调用
        raise AssertionError("超限时不能再把整表读进内存")

    monkeypatch.setattr(module.repo, "count_all", fake_count)
    monkeypatch.setattr(module.repo, "list_all", fail_list_all)

    with pytest.raises(ApiError) as exc:
        asyncio.run(getattr(module, export_fn)(object(), _FakeActor()))
    assert exc.value.http_status == 422
    assert str(limit) in exc.value.message


def test_export_allows_exactly_at_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """正好等于上限要放行，上限是「超过才拒绝」。"""

    limit = get_settings().export_max_rows

    async def fake_count(_session: object) -> int:
        return limit

    async def fake_list_all(_session: object) -> list[object]:
        return []

    async def fake_enqueue(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(sources.repo, "count_all", fake_count)
    monkeypatch.setattr(sources.repo, "list_all", fake_list_all)
    monkeypatch.setattr(sources, "enqueue_event", fake_enqueue)

    payload = asyncio.run(sources.export_sources(object(), _FakeActor()))
    assert payload[:2] == b"PK"  # 正常生成了 xlsx


def test_default_export_limit_is_100k() -> None:
    assert get_settings().export_max_rows == 100_000
