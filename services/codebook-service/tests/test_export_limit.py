"""导出行数上限与导出筛选的回归测试。"""

from __future__ import annotations

import asyncio

import pytest

# 与 test_route_security_class.py 一致：导入 app 模块前必须先给出数据库配置。
from platform_common.errors import ApiError

from app.application import area_codes, policy_types, scenarios
from app.core.config import get_settings

MODULES = [
    (scenarios, "export_scenarios", {"industry_l1": "制造"}),
    (policy_types, "export_policy_types", {"keyword": "补贴"}),
    (area_codes, "export_area_codes", {"prov_name": "北京市"}),
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
    assert payload[:2] == b"PK"
    assert seen["count"] == filters
    assert seen["list"] == filters


def test_default_export_limit_is_100k() -> None:
    assert get_settings().export_max_rows == 100_000
