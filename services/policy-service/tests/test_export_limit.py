"""导出行数上限与导出筛选的回归测试。"""

from __future__ import annotations

import asyncio
import os

import pytest

# 与 test_route_security_class.py 一致：导入 app 模块前必须先给出数据库配置。
os.environ.setdefault("POLICY_DATABASE_URL", "postgresql+asyncpg://policy_app:test@localhost:5432/policy_db")

from platform_common.errors import ApiError

from app.application import base_tags, interpretations, sources
from app.core.config import get_settings

MODULES = [
    (sources, "export_sources", {"site_name": "北京"}),
    (base_tags, "export_base_tags", {"policy_name": "补贴"}),
    (interpretations, "export_interpretations", {"policy_title": "补贴"}),
]


class _FakeActor:
    id = "u1"
    name = "测试"


@pytest.mark.parametrize(("module", "export_fn", "filters"), MODULES)
def test_export_rejects_when_over_limit(
    monkeypatch: pytest.MonkeyPatch, module, export_fn: str, filters: dict[str, str]
) -> None:
    limit = get_settings().export_max_rows

    async def fake_count(_session: object, _filters: object) -> int:
        return limit + 1

    def fail_list(_session: object, _filters: object) -> None:  # pragma: no cover - 不应被调用
        raise AssertionError("超限时不能再把结果集读进内存")

    monkeypatch.setattr(module.repo, "count_filtered", fake_count)
    monkeypatch.setattr(module.repo, "list_filtered", fail_list)

    with pytest.raises(ApiError) as exc:
        asyncio.run(getattr(module, export_fn)(object(), _FakeActor(), dict(filters)))
    assert exc.value.http_status == 422
    assert str(limit) in exc.value.message


@pytest.mark.parametrize(("module", "export_fn", "filters"), MODULES)
def test_export_passes_filters_to_repository(
    monkeypatch: pytest.MonkeyPatch, module, export_fn: str, filters: dict[str, str]
) -> None:
    """导出必须把筛选条件原样交给仓储，否则「所见即所导」就不成立。"""

    seen: dict[str, object] = {}

    async def fake_count(_session: object, passed: object) -> int:
        seen["count"] = passed
        return 1

    async def fake_list(_session: object, passed: object) -> list[object]:
        seen["list"] = passed
        return []

    async def fake_enqueue(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(module.repo, "count_filtered", fake_count)
    monkeypatch.setattr(module.repo, "list_filtered", fake_list)
    monkeypatch.setattr(module, "enqueue_event", fake_enqueue)

    payload = asyncio.run(getattr(module, export_fn)(object(), _FakeActor(), dict(filters)))
    assert payload[:2] == b"PK"  # 正常生成了 xlsx
    assert seen["count"] == filters
    assert seen["list"] == filters


def test_over_limit_message_distinguishes_filtered_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """有筛选时提示「筛选结果」，无筛选时提示「本表」。"""

    limit = get_settings().export_max_rows

    async def fake_count(_session: object, _filters: object) -> int:
        return limit + 1

    monkeypatch.setattr(sources.repo, "count_filtered", fake_count)

    with pytest.raises(ApiError) as filtered:
        asyncio.run(sources.export_sources(object(), _FakeActor(), {"site_name": "北京"}))
    assert filtered.value.message.startswith("筛选结果共")

    with pytest.raises(ApiError) as whole:
        asyncio.run(sources.export_sources(object(), _FakeActor(), {"site_name": None}))
    assert whole.value.message.startswith("本表共")


def test_export_allows_exactly_at_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """正好等于上限要放行，上限是「超过才拒绝」。"""

    limit = get_settings().export_max_rows

    async def fake_count(_session: object, _filters: object) -> int:
        return limit

    async def fake_list(_session: object, _filters: object) -> list[object]:
        return []

    async def fake_enqueue(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(sources.repo, "count_filtered", fake_count)
    monkeypatch.setattr(sources.repo, "list_filtered", fake_list)
    monkeypatch.setattr(sources, "enqueue_event", fake_enqueue)

    assert asyncio.run(sources.export_sources(object(), _FakeActor(), {}))[:2] == b"PK"


def test_default_export_limit_is_100k() -> None:
    assert get_settings().export_max_rows == 100_000
