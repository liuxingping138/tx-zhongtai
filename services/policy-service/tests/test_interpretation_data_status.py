"""政策解读：数据状态字段与新增筛选项的回归测试。"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import pytest

# 与 test_route_security_class.py 一致：导入 app 模块前必须先给出数据库配置。
os.environ.setdefault("POLICY_DATABASE_URL", "postgresql+asyncpg://policy_app:test@localhost:5432/policy_db")

from openpyxl import Workbook
from platform_common.columns import header_to_field
from platform_common.errors import ApiError
from sqlalchemy.dialects import postgresql

from app.policy.application import interpretations as service
from app.policy.domain.fields import DATA_STATUS_CHOICES, INTERPRETATION_COLUMNS
from app.policy.domain.models import INTERPRETATION_WRITE_FIELDS, Interpretation
from app.policy.repositories import interpretations as repo


class _FakeActor:
    id = "u1"
    name = "测试"


def _sql(filters: dict[str, Any]) -> str:
    conds = repo._conditions(filters)
    return " AND ".join(str(cond.compile(dialect=postgresql.dialect())) for cond in conds)


def test_new_filters_are_registered_for_list_and_export() -> None:
    assert {"scenario_l1_name", "is_new_scenario", "new_scenario_level", "info_level", "data_status"} <= set(
        repo.FILTER_COLUMNS
    )


def test_enum_filters_match_exactly_and_names_match_fuzzily() -> None:
    """枚举字段精确匹配，避免「一级」把「一级场景」也查出来；一级场景名称仍是模糊匹配。"""

    for field in ("is_new_scenario", "new_scenario_level", "info_level", "data_status"):
        sql = _sql({field: ["x"]})
        assert " IN " in sql and "ILIKE" not in sql.upper(), field
    assert "ILIKE" in _sql({"scenario_l1_name": ["x"]}).upper()


def test_empty_new_filters_do_not_filter() -> None:
    assert repo._conditions({"data_status": None, "info_level": [], "scenario_l1_name": [""]}) == []


def test_data_status_header_is_recognised() -> None:
    assert header_to_field(INTERPRETATION_COLUMNS, "数据状态") == "data_status"
    assert header_to_field(INTERPRETATION_COLUMNS, "信息化等级") == "info_level"


def test_blank_status_defaults_to_pending() -> None:
    values = service._values(dict.fromkeys(INTERPRETATION_WRITE_FIELDS, "") | {"policy_title": "某政策"})
    assert values["data_status"] == "待验证"


def test_status_choices_are_the_two_agreed_values() -> None:
    assert DATA_STATUS_CHOICES == ("待验证", "人工验证")
    for value in DATA_STATUS_CHOICES:
        assert service._data_status_error({"data_status": value}) is None
    assert service._data_status_error({"data_status": "已验证"}) is not None


def test_create_rejects_unknown_status() -> None:
    with pytest.raises(ApiError) as exc:
        asyncio.run(
            service.create_interpretation(object(), _FakeActor(), {"policy_title": "某政策", "data_status": "已验证"})
        )
    assert exc.value.http_status == 422
    assert "数据状态" in exc.value.message


def _row(status: str) -> Interpretation:
    now = datetime.now(UTC)
    values = dict.fromkeys(INTERPRETATION_WRITE_FIELDS, "")
    values.update(policy_title="某政策", policy_uid="uid-1", data_status=status)
    return Interpretation(
        id=uuid.uuid4(),
        record_id="r1",
        relation_key="uid-1",
        version=3,
        created_at=now,
        created_by_id="u0",
        created_by_name="录入人",
        updated_at=now,
        updated_by_id="u0",
        updated_by_name="录入人",
        **values,
    )


def _patch_update(monkeypatch: pytest.MonkeyPatch, row: Interpretation) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    async def locked(_session: object, _item_id: object) -> Interpretation:
        return row

    async def no_duplicate(_session: object, _key: str) -> None:
        return None

    async def fake_enqueue(*_args: object, **kwargs: Any) -> None:
        events.append(kwargs)

    monkeypatch.setattr(service.repo, "get_for_update", locked)
    monkeypatch.setattr(service.repo, "get_by_relation_key", no_duplicate)
    monkeypatch.setattr(service, "enqueue_event", fake_enqueue)
    return events


def test_update_without_status_keeps_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    """请求没带数据状态（旧客户端）时不能把人工验证冲回待验证。"""

    row = _row("人工验证")
    _patch_update(monkeypatch, row)
    out = asyncio.run(
        service.update_interpretation(
            object(), _FakeActor(), row.id, {"version": 3, "policy_title": "某政策", "opportunity_type": "TO_G"}
        )
    )
    assert out["data_status"] == "人工验证"


def test_update_can_mark_manually_verified_and_records_change(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row("待验证")
    events = _patch_update(monkeypatch, row)
    out = asyncio.run(
        service.update_interpretation(
            object(), _FakeActor(), row.id, {"version": 3, "policy_title": "某政策", "data_status": "人工验证"}
        )
    )
    assert out["data_status"] == "人工验证"
    assert events[0]["changes"]["data_status"] == {"from": "待验证", "to": "人工验证"}


def test_update_rejects_unknown_status(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row("待验证")
    _patch_update(monkeypatch, row)
    with pytest.raises(ApiError) as exc:
        asyncio.run(
            service.update_interpretation(
                object(), _FakeActor(), row.id, {"version": 3, "policy_title": "某政策", "data_status": "乱填"}
            )
        )
    assert exc.value.http_status == 422


class _ImportSession:
    def __init__(self) -> None:
        self.added: list[Interpretation] = []

    def add(self, row: Interpretation) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        return None


def _workbook(rows: list[list[str]]) -> bytes:
    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    raw = BytesIO()
    book.save(raw)
    return raw.getvalue()


def test_import_defaults_and_validates_status(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_keys(_session: object) -> set[str]:
        return set()

    async def fake_enqueue(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(service.repo, "list_relation_keys", no_keys)
    monkeypatch.setattr(service, "enqueue_event", fake_enqueue)

    session = _ImportSession()
    content = _workbook(
        [
            ["政策原文名称", "机会类型", "数据状态"],
            ["政策甲", "TO_G", ""],  # 未填：默认待验证
            ["政策乙", "TO_G", "人工验证"],
            ["政策丙", "TO_G", "已验证"],  # 非法：跳过
        ]
    )
    result = asyncio.run(service.import_interpretations(session, _FakeActor(), content))  # type: ignore[arg-type]

    assert result["inserted"] == 2
    assert result["skipped"] == 1
    assert {row.policy_title: row.data_status for row in session.added} == {
        "政策甲": "待验证",
        "政策乙": "人工验证",
    }


def test_import_without_status_column_defaults_to_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    """旧模板没有「数据状态」列，也要能导入，且全部按待验证入库。"""

    async def no_keys(_session: object) -> set[str]:
        return set()

    async def fake_enqueue(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(service.repo, "list_relation_keys", no_keys)
    monkeypatch.setattr(service, "enqueue_event", fake_enqueue)

    session = _ImportSession()
    content = _workbook([["政策原文名称", "机会类型"], ["政策甲", "TO_G"]])
    result = asyncio.run(service.import_interpretations(session, _FakeActor(), content))  # type: ignore[arg-type]

    assert result["inserted"] == 1
    assert session.added[0].data_status == "待验证"
