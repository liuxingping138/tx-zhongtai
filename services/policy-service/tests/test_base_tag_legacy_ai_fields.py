"""「是否信息化政策」「信息化标签」已从基础标签去掉：老数据 ai_outputs 里还留着、旧的上线模板还在输出，
列表、详情、导出、编辑和动态列都不能再把它们带出来。"""

from __future__ import annotations

import uuid
from io import BytesIO
from typing import Any

import pytest
from openpyxl import load_workbook

from app.policy.application import base_tags
from app.policy.domain.fields import BASE_TAG_COLUMNS
from app.policy.domain.models import BaseTag

LEGACY = {"是否信息化政策": "是", "信息化标签": "数字政府、政务云"}


def _row() -> BaseTag:
    values: dict[str, Any] = {spec.field: "" for spec in BASE_TAG_COLUMNS}
    values.update(policy_name="政策A", need_interpret="是", policy_types="信息化建设类")
    return BaseTag(id=uuid.uuid4(), version=3, ai_outputs={"是否政策": "是", "判定简因": "政务云", **LEGACY}, **values)


def test_list_and_detail_hide_the_removed_fields() -> None:
    out = base_tags._to_out(_row())
    assert not set(LEGACY) & set(out) and not set(LEGACY) & set(out["ai_outputs"])
    assert (out["是否政策"], out["判定简因"], out["ai_outputs"]) == (
        "是",
        "政务云",
        {"是否政策": "是", "判定简因": "政务云"},
    )
    # 以前「是否信息化政策」空着时拿「是否解读」顶上，现在不再有这一列
    bare = _row()
    bare.ai_outputs = {}
    assert "是否信息化政策" not in base_tags._to_out(bare) and base_tags._to_out(bare)["是否政策"] == ""


def test_editing_ignores_and_drops_the_removed_fields() -> None:
    row = _row()
    changes = base_tags._apply_ai_outputs(row, {"信息化标签": "改了", "是否信息化政策": "否", "判定简因": "新理由"})
    assert changes == {"判定简因": {"from": "政务云", "to": "新理由"}}
    assert row.ai_outputs == {"是否政策": "是", "判定简因": "新理由"}
    untouched = _row()
    assert base_tags._apply_ai_outputs(untouched, dict(LEGACY)) == {} and "信息化标签" in untouched.ai_outputs


async def test_export_and_dynamic_columns_leave_out_the_removed_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    async def count(*_: Any) -> int:
        return 1

    async def rows(*_: Any) -> list[Any]:
        return [_row()]

    async def nothing(*_: Any, **__: Any) -> None:
        return None

    async def templates(*_: Any, **__: Any) -> list[dict[str, Any]]:
        return [{"output_fields": ["是否政策", "政策类型", "是否信息化政策", "信息化标签", "判定简因", "依据"]}]

    monkeypatch.setattr(base_tags.repo, "count_filtered", count)
    monkeypatch.setattr(base_tags.repo, "list_filtered", rows)
    monkeypatch.setattr(base_tags, "attach_policy_contents", nothing)
    monkeypatch.setattr(base_tags, "enqueue_event", nothing)
    monkeypatch.setattr(base_tags.internal_clients, "ai", templates)
    actor: Any = type("Actor", (), {"id": "u1", "name": "管理员"})()
    book = load_workbook(BytesIO(await base_tags.export_base_tags(object(), actor, {})))  # type: ignore[arg-type]
    headers = [cell.value for cell in next(book.active.iter_rows(max_row=1))]  # type: ignore[union-attr]
    assert "是否政策" in headers and "判定简因" in headers and not set(LEGACY) & set(headers)
    assert await base_tags._active_ai_fields() == ["是否政策", "判定简因", "依据"]
