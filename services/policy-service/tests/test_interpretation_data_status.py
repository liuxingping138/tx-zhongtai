"""政策解读：数据状态字段与新增筛选项的回归测试。"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import pytest

# 与 test_route_security_class.py 一致：导入 app 模块前必须先给出数据库配置。
from openpyxl import Workbook
from platform_common.columns import header_to_field
from platform_common.errors import ApiError, DependencyUnavailableError
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
    """枚举字段和候选值取自码表的一级行业、一级场景精确匹配（走索引，「一级」也不会把「一级场景」查出来）；
    政策原文名称是关键词，模糊匹配。"""

    for field in (
        "industry_l1",
        "scenario_l1_name",
        "is_new_scenario",
        "new_scenario_level",
        "info_level",
        "data_status",
    ):
        sql = _sql({field: ["x"]})
        assert " IN " in sql and "ILIKE" not in sql.upper(), field
    assert "ILIKE" in _sql({"policy_title": ["x"]}).upper()


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
    async def no_keys(_session: object, _keys: object) -> set[str]:
        return set()

    async def fake_enqueue(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(service.repo, "existing_relation_keys", no_keys)
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

    async def no_keys(_session: object, _keys: object) -> set[str]:
        return set()

    async def fake_enqueue(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(service.repo, "existing_relation_keys", no_keys)
    monkeypatch.setattr(service, "enqueue_event", fake_enqueue)

    session = _ImportSession()
    content = _workbook([["政策原文名称", "机会类型"], ["政策甲", "TO_G"]])
    result = asyncio.run(service.import_interpretations(session, _FakeActor(), content))  # type: ignore[arg-type]

    assert result["inserted"] == 1
    assert session.added[0].data_status == "待验证"


def _named(row: Interpretation, **codes: str) -> Interpretation:
    row.industry_l1, row.industry_l2, row.industry_l3 = "医卫行业", "卫生、社会保障和社会福利业", "卫生"
    row.scenario_l1_name, row.scenario_l2_name = "视联网", "千里眼"
    for field, value in codes.items():
        setattr(row, field, value)
    return row


def _form(row: Interpretation, **changes: Any) -> dict[str, Any]:
    return {**{field: getattr(row, field) or "" for field in INTERPRETATION_WRITE_FIELDS}, "version": 3, **changes}


def _codebook(monkeypatch: pytest.MonkeyPatch, answer: dict[str, str] | Exception) -> list[dict[str, Any]]:
    asked: list[dict[str, Any]] = []

    async def lookup(_method: str, _path: str, **kwargs: Any) -> list[dict[str, str]]:
        asked.append(kwargs["json"]["items"][0])
        if isinstance(answer, Exception):
            raise answer
        return [{"key": "0", **answer}]

    monkeypatch.setattr(service.internal_clients, "codebook", lookup)
    return asked


GENERAL_CODES = {
    "industry_code": "03000000",
    "scenario_code": "221549000000",
    "industry_scenario_code": "03000000221549000000",
}


def test_renaming_the_scenario_looks_the_codes_up_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """改了场景名称，旧编码就是别的场景的了：按新名称重查，查不到清空。"""

    row = _named(
        _row("待验证"), industry_code="03010100", scenario_code="100000000000", industry_scenario_code="0301010010"
    )
    events = _patch_update(monkeypatch, row)
    asked = _codebook(monkeypatch, {"industry_code": "", "scenario_code": "", "industry_scenario_code": ""})
    out = asyncio.run(
        service.update_interpretation(object(), _FakeActor(), row.id, _form(row, scenario_l2_name="顺风耳"))
    )
    assert asked[0]["scenario_l2_name"] == "顺风耳"
    assert (out["industry_code"], out["industry_scenario_code"]) == ("", "")
    assert events[0]["changes"]["industry_scenario_code"]["to"] == ""


def test_saving_a_row_without_codes_fills_them_in(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _named(_row("待验证"))
    _patch_update(monkeypatch, row)
    _codebook(monkeypatch, GENERAL_CODES)
    out = asyncio.run(service.update_interpretation(object(), _FakeActor(), row.id, _form(row, remark="核对过")))
    assert out["industry_scenario_code"] == "03000000221549000000"


def test_rows_that_have_codes_and_keep_their_names_do_not_ask_the_codebook(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _named(_row("待验证"), **GENERAL_CODES)
    _patch_update(monkeypatch, row)
    asked = _codebook(monkeypatch, {})
    asyncio.run(service.update_interpretation(object(), _FakeActor(), row.id, _form(row, remark="核对过")))
    assert asked == []


def test_renaming_a_synced_new_scenario_lets_it_sync_again(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _named(_row("人工验证"), **GENERAL_CODES)
    row.is_new_scenario, row.scenario_synced_at = "是", datetime.now(UTC)
    events = _patch_update(monkeypatch, row)
    _codebook(monkeypatch, {"industry_code": "", "scenario_code": "", "industry_scenario_code": ""})
    asyncio.run(
        service.update_interpretation(object(), _FakeActor(), row.id, _form(row, scenario_l1_name="视联网二期"))
    )
    assert row.scenario_synced_at is None
    assert "scenario_synced_at" in events[0]["changes"]


def test_codebook_outage_blocks_only_a_rename(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _named(_row("待验证"))
    _patch_update(monkeypatch, row)
    _codebook(monkeypatch, DependencyUnavailableError())
    # 只是顺手补查编码：码表连不上照样保存。
    out = asyncio.run(service.update_interpretation(object(), _FakeActor(), row.id, _form(row, remark="核对过")))
    assert out["remark"] == "核对过"
    with pytest.raises(DependencyUnavailableError, match="改了行业场景名称"):
        asyncio.run(
            service.update_interpretation(
                object(), _FakeActor(), row.id, _form(row, version=4, scenario_l1_name="别的")
            )
        )
