"""数据库抽样（市场机会）按一级行业筛选时挑哪些解读行。"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.aitag.application.samples import SampleFilter, _sample_pairs

_DONE = datetime(2026, 11, 1, tzinfo=UTC)
_LATER = datetime(2026, 11, 2, tzinfo=UTC)


def _row(industry: str, scenario: str, *, edited: bool) -> SimpleNamespace:
    return SimpleNamespace(
        industry_l1=industry,
        scenario_l1_name=scenario,
        data_status="待验证",
        tagged_at=_DONE,
        updated_at=_LATER if edited else _DONE,
        source_content_id="c1",
    )


def test_industry_filter_falls_back_to_edited_rows_of_that_industry() -> None:
    # 这个行业的行都被人改过，别的行业还有 AI 行：仍要拿到这个行业的组
    rows = [_row("教育", "智慧校园", edited=False), _row("医疗", "智慧医院", edited=True)]
    assert _sample_pairs(rows, "医疗") == [{"industry_l1": "医疗", "scenario_l1_name": "智慧医院"}]


def test_prefers_untouched_rows_within_the_industry() -> None:
    rows = [_row("医疗", "智慧医院", edited=False), _row("医疗", "互联网医院", edited=True)]
    assert _sample_pairs(rows, "医疗") == [{"industry_l1": "医疗", "scenario_l1_name": "智慧医院"}]


def test_no_filter_prefers_untouched_rows() -> None:
    rows = [_row("教育", "智慧校园", edited=False), _row("医疗", "智慧医院", edited=True)]
    assert _sample_pairs(rows, "") == [{"industry_l1": "教育", "scenario_l1_name": "智慧校园"}]


def test_blank_untouched_row_does_not_shadow_named_edited_row() -> None:
    # 未改过的 AI 行缺少场景名称时不能遮挡人工已补齐场景名的行，否则展开后一组也取不到
    rows = [_row("医疗", "", edited=False), _row("医疗", "智慧医院", edited=True)]
    assert _sample_pairs(rows, "医疗") == [{"industry_l1": "医疗", "scenario_l1_name": "智慧医院"}]


def test_sample_filter_active_for_ignores_industry_on_non_opportunity_tasks() -> None:
    flt = SampleFilter(industry_l1="党政行业")
    assert flt.active_for("opportunity") is True
    assert flt.active_for("interpret") is False
    assert SampleFilter(keyword="算力").active_for("interpret") is True
