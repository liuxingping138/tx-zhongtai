"""导出行数上限的回归测试。"""

from __future__ import annotations

import asyncio
import os

import pytest

# 与 test_route_security_class.py 一致：导入 app 模块前必须先给出数据库配置。
os.environ.setdefault("CODEBOOK_DATABASE_URL", "postgresql+asyncpg://codebook_app:test@localhost:5432/codebook_db")

from platform_common.errors import ApiError

from app.application import area_codes, policy_types, scenarios
from app.core.config import get_settings


class _FakeActor:
    id = "u1"
    name = "测试"


@pytest.mark.parametrize(
    ("module", "export_fn"),
    [
        (scenarios, "export_scenarios"),
        (policy_types, "export_policy_types"),
        (area_codes, "export_area_codes"),
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


def test_default_export_limit_is_100k() -> None:
    assert get_settings().export_max_rows == 100_000
