from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.model_configs import to_model
from app.domain.llm_models import build_body, calc_costs, in_peak, parse_peak_hours
from app.domain.templating import (
    CODE_TABLE_FIELD,
    build_myid,
    extract_fields,
    fill_template,
    split_fields,
    template_variables,
)
from tests.helpers import NOW, ai_model, sample_models


def test_fill_template_replaces_columns_and_code_table_and_keeps_unknown() -> None:
    content = "企业：@【企业名称】，地址：@【 地址 】，码表：@【上传码表】，未知：@【电话】"
    filled = fill_template(content, {"企业名称": "甲公司", "地址": "北京"}, "A\tB")
    assert filled == "企业：甲公司，地址：北京，码表：A\tB，未知：@【电话】"
    assert template_variables(content) == ["企业名称", "地址", CODE_TABLE_FIELD, "电话"]


def test_split_fields_trims_and_drops_empty() -> None:
    assert split_fields(" 行业 | |场景|") == ["行业", "场景"]
    assert split_fields("") == []


def test_myid_matches_legacy_numbering() -> None:
    assert [build_myid(0), build_myid(9)] == ["a1000001", "a1000010"]


def test_extract_fields_expands_every_entry_and_fills_missing_keys() -> None:
    text = '好的：[{"行业":"制造","场景":"质检"},{"行业":"能源"}] 以上'
    assert extract_fields(text, ["行业", "场景"]) == [
        {"行业": "制造", "场景": "质检"},
        {"行业": "能源", "场景": ""},
    ]


def test_extract_fields_rescues_stray_backslashes() -> None:
    text = r'[{"公式":"\alpha + 1","路径":"C:\temp"}]'
    assert extract_fields(text, ["公式", "路径"]) == [{"公式": r"\alpha + 1", "路径": "C:\temp"}]


def test_extract_fields_returns_one_empty_row_when_unparseable() -> None:
    empty = [{"行业": ""}]
    assert extract_fields("没有 JSON", ["行业"]) == empty
    assert extract_fields('[{"行业": 坏}]', ["行业"]) == empty
    assert extract_fields("", ["行业"]) == empty
    assert extract_fields('[{"x": null}]', []) == [{}]


def test_build_body_controls_thinking_only_where_supported() -> None:
    ark, baidu = (to_model(row) for row in sample_models())
    assert build_body(baidu, "hi", thinking=False)["thinking"] == {"type": "disabled"}
    assert "service_tier" not in build_body(baidu, "hi") and "reasoning" not in build_body(baidu, "hi")
    ark_body = build_body(ark, "hi", thinking=False)
    assert ark_body["thinking"] == {"type": "enabled"} and ark_body["tools"][0]["type"] == "web_search"
    assert ark_body["service_tier"] == "flex" and ark_body["reasoning"] == {"effort": "low"}
    assert ark_body["model"] == "ep-flash" and ark_body["stream"] is True


def test_flex_tier_bills_at_flex_prices() -> None:
    flash = to_model(ai_model())
    inference, search = calc_costs(flash, 2000, 1000, 3, NOW)
    assert inference == Decimal("0.007500")  # 2×0.0015 + 1×0.0045
    assert search == Decimal("0.012000")
    regular = to_model(ai_model(service_tier="auto"))
    assert calc_costs(regular, 2000, 1000, 0, NOW)[0] == Decimal("0.015000")


# 2026-10-21 是周三，2026-10-24 是周六；时间都是北京时间。
_BEIJING = timezone(timedelta(hours=8))


@pytest.mark.parametrize(
    ("moment", "peak"),
    [
        (datetime(2026, 10, 21, 9, 0, tzinfo=_BEIJING), True),
        (datetime(2026, 10, 21, 11, 59, tzinfo=_BEIJING), True),
        (datetime(2026, 10, 21, 12, 0, tzinfo=_BEIJING), False),
        (datetime(2026, 10, 21, 13, 30, tzinfo=_BEIJING), False),
        (datetime(2026, 10, 21, 17, 59, tzinfo=_BEIJING), True),
        (datetime(2026, 10, 21, 20, 0, tzinfo=_BEIJING), False),
        (datetime(2026, 10, 24, 10, 0, tzinfo=_BEIJING), False),
        (datetime(2026, 10, 21, 2, 0, tzinfo=UTC), True),  # 北京 10:00
    ],
)
def test_peak_hours_follow_beijing_weekdays(moment: datetime, peak: bool) -> None:
    assert in_peak(moment, "09:00-12:00,14:00-18:00") is peak


def test_peak_hours_can_end_at_midnight_and_bad_clock_times_name_the_part() -> None:
    """「18:00-24:00」是常见写法；time 只到 23 点，原来报的是英文的 hour must be in 0..23。"""

    assert in_peak(datetime(2026, 10, 21, 23, 59, tzinfo=_BEIJING), "18:00-24:00") is True
    assert in_peak(datetime(2026, 10, 21, 17, 59, tzinfo=_BEIJING), "18:00-24:00") is False
    for text in ("24:00-25:00", "09:60-10:00", "10:00-09:00"):
        with pytest.raises(ValueError, match=text.split(",")[0]):
            parse_peak_hours(text)


def test_time_of_day_prices_switch_between_peak_and_idle() -> None:
    economy = to_model(
        ai_model(
            service_tier="",
            input_price=Decimal("0.0008"),
            output_price=Decimal("0.0032"),
            flex_input_price=None,
            flex_output_price=None,
            peak_input_price=Decimal("0.0016"),
            peak_output_price=Decimal("0.0064"),
            peak_hours="09:00-12:00,14:00-18:00",
        )
    )
    busy = datetime(2026, 10, 21, 10, 0, tzinfo=_BEIJING)
    idle = datetime(2026, 10, 21, 22, 0, tzinfo=_BEIJING)
    assert economy.prices_at(busy) == (Decimal("0.0016"), Decimal("0.0064"))
    assert economy.prices_at(idle) == (Decimal("0.0008"), Decimal("0.0032"))
    assert calc_costs(economy, 1000, 1000, 0, busy)[0] == 2 * calc_costs(economy, 1000, 1000, 0, idle)[0]
    # 页面价格旁边写清是哪一档：高峰、平时；低优档的不看时段。
    assert economy.price_note(busy) == "高峰价（工作日 09:00-12:00、14:00-18:00）"
    assert economy.price_note(idle) == "平时价（工作日 09:00-12:00、14:00-18:00 涨价）"
    flex = replace(
        economy, service_tier="flex", flex_input_price=Decimal("0.0004"), flex_output_price=Decimal("0.0016")
    )
    assert flex.price_note(busy) == "低优档"
    assert replace(economy, peak_input_price=None).price_note(busy) == ""


def test_parse_fields_tolerates_wrapping_nesting_and_single_objects() -> None:
    from app.domain.templating import parse_fields

    fields = ["行业", "客群"]
    fenced = '说明如下：\n```json\n[{"行业": "制造", "客群": "大企业"}]\n```\n以上。'
    assert parse_fields(fenced, fields) == [{"行业": "制造", "客群": "大企业"}]
    nested = '[{"行业": "制造", "客群": "a}]b", "依据": [{"条款": 1}]}, {"行业": "零售", "客群": null}]'
    assert parse_fields(nested, fields) == [{"行业": "制造", "客群": "a}]b"}, {"行业": "零售", "客群": ""}]
    assert parse_fields('结果 {"行业": "能源"}', fields) == [{"行业": "能源", "客群": ""}]
    preferring = '示例格式 [{"字段": "值"}]，实际结果 [{"行业": "教育"}]'
    assert parse_fields(preferring, fields) == [{"行业": "教育", "客群": ""}]
    assert parse_fields('[{"行业": "C:\\path\\x"}]', ["行业"]) == [{"行业": "C:\\path\\x"}]
    for unusable in ("", "没有 JSON", '[{"别的": 1}]', "[1, 2]", "[{坏的"):
        assert parse_fields(unusable, fields) is None
    assert parse_fields('[{"行业": 1}]', []) is None
    thinking_hijack = (
        '<think>比如正文写了 [{"行业": "假"}]</think>\n前缀 {"行业": " prose"}\n```json\n[{"行业": "真"}]\n```'
    )
    assert parse_fields(thinking_hijack, fields) == [{"行业": "真", "客群": ""}]


def test_parse_fields_rejects_truncated_or_broken_multi_item_json_arrays() -> None:
    """截断或第 2..N 项语法损坏的 JSON 数组绝不能退化为只返回第 1 项，必须返回 None 触发格式重试。"""

    from app.domain.templating import parse_fields

    fields = ["行业", "客群"]
    truncated = '[{"行业": "政务", "客群": "政府"}, {"行业": "医疗", "客群": "医院"}, {"行业": "教育", "客群": '
    assert parse_fields(truncated, fields) is None

    broken_second = '[{"行业": "政务", "客群": "政府"}, {"行业": "医"疗", "客群": "医院"}]'
    assert parse_fields(broken_second, fields) is None

    fenced_truncated = '```json\n[\n  {"行业": "政务", "客群": "政府"},\n  {"行业": "医疗"\n```'
    assert parse_fields(fenced_truncated, fields) is None

    # 正文里普通的非 JSON 方括号提示不影响后面的合法单对象。
    assert parse_fields('[提示] {"行业": "能源", "客群": "国企"}', fields) == [{"行业": "能源", "客群": "国企"}]
    # 第 2 项带非法反斜杠时，不会提前截胡第 1 项，而是走 _clean_json 完整救回两项。
    stray_bs = r'[{"行业": "政务", "客群": "政府"}, {"行业": "C:\alpha", "客群": "医疗"}]'
    assert parse_fields(stray_bs, fields) == [
        {"行业": "政务", "客群": "政府"},
        {"行业": r"C:\alpha", "客群": "医疗"},
    ]
