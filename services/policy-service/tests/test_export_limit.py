"""导出行数上限与导出筛选的回归测试。"""

from __future__ import annotations

import asyncio
import uuid
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from openpyxl import load_workbook
from platform_common.errors import ApiError

from app.core.config import get_settings
from app.policy.application import base_tags, interpretations, sources
from app.policy.application.policy_content import content_export_limit

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
    # 基础标签、解读的导出带政策正文，上限是更小的正文导出上限
    limit = get_settings().export_max_rows if module is sources else content_export_limit()

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


def test_exports_with_policy_content_are_capped_lower() -> None:
    # 带正文的导出要逐批到源库读，10 万行要十几分钟：默认最多 2 万行。
    assert get_settings().export_content_max_rows == 20_000
    assert content_export_limit() == 20_000


def test_export_base_tags_and_interpretations_include_policy_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证政策基础表与政策解读表导出均包含「政策正文」列与内容。"""
    item_base = SimpleNamespace(
        id=uuid.uuid4(),
        source_content_id="src_1",
        policy_name="政策A",
        issuing_dept="",
        issuer_industry="",
        policy_level="",
        province_code="",
        province_name="北京",
        city_code="",
        city_name="",
        issued_at="2026-01-01",
        policy_types="",
        source_url="",
        is_penetrate="",
        penetrate_words="",
        penetrate_score="",
        need_interpret="是",
        remark="",
        version=1,
        created_at=None,
        created_by_name="",
        updated_at=None,
        updated_by_name="",
        type_retag_at=None,
        interpreted_at=None,
        opportunity_at=None,
    )
    item_base.business_values = lambda: {
        spec.field: getattr(item_base, spec.field, "") for spec in base_tags.BASE_TAG_COLUMNS
    }

    item_interp = SimpleNamespace(
        id=uuid.uuid4(),
        record_id="rec_1",
        tenant_id="t1",
        policy_uid="u1",
        policy_title="政策A",
        industry_scenario_code="",
        industry_code="",
        industry_l1="",
        industry_l2="",
        industry_l3="",
        scenario_code="",
        scenario_l1_name="",
        scenario_l2_name="",
        scenario_l3_name="",
        target_customers="",
        adapted_products="",
        purchase_reason="",
        relation_key="",
        opportunity_type="",
        policy_summary="要文",
        has_subsidy="",
        subsidy_content="",
        market_opportunity="",
        info_level="",
        is_new_scenario="",
        new_scenario_level="",
        remark="",
        data_status="待验证",
        scenario_state="",
        candidate_id=None,
        source_content_id="src_1",
        tagged_at=None,
        scenario_synced_at=None,
        version=1,
        created_at=None,
        created_by_name="",
        updated_at=None,
        updated_by_name="",
    )

    async def fake_count(_session: object, _filters: object) -> int:
        return 1

    async def fake_list_base(_session: object, _filters: object) -> list[object]:
        return [item_base]

    async def fake_list_interp(_session: object, _filters: object) -> list[object]:
        return [item_interp]

    async def fake_attach(_session: object, _items: object, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            row["policy_content"] = "这是政策正文测试内容"

    async def fake_enqueue(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(base_tags.repo, "count_filtered", fake_count)
    monkeypatch.setattr(base_tags.repo, "list_filtered", fake_list_base)
    monkeypatch.setattr(base_tags, "attach_policy_contents", fake_attach)
    monkeypatch.setattr(base_tags, "enqueue_event", fake_enqueue)

    monkeypatch.setattr(interpretations.repo, "count_filtered", fake_count)
    monkeypatch.setattr(interpretations.repo, "list_filtered", fake_list_interp)
    monkeypatch.setattr(interpretations, "attach_policy_contents", fake_attach)
    monkeypatch.setattr(interpretations, "enqueue_event", fake_enqueue)

    # 1. 验证基础标签表
    payload_base = asyncio.run(base_tags.export_base_tags(object(), _FakeActor(), {}))
    wb_base = load_workbook(BytesIO(payload_base))
    headers_base = [cell.value for cell in wb_base.active[1]]
    assert "政策正文" in headers_base
    base_idx = headers_base.index("政策正文") + 1
    assert wb_base.active.cell(row=2, column=base_idx).value == "这是政策正文测试内容"

    # 2. 验证政策解读表
    payload_interp = asyncio.run(interpretations.export_interpretations(object(), _FakeActor(), {}))
    wb_interp = load_workbook(BytesIO(payload_interp))
    headers_interp = [cell.value for cell in wb_interp.active[1]]
    assert "政策正文" in headers_interp
    interp_idx = headers_interp.index("政策正文") + 1
    assert wb_interp.active.cell(row=2, column=interp_idx).value == "这是政策正文测试内容"
