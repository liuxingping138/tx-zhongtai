from __future__ import annotations

from decimal import Decimal

from app.domain.llm_models import build_body, calc_costs, find_model, model_display_name
from app.domain.templating import (
    CODE_TABLE_FIELD,
    build_myid,
    extract_fields,
    fill_template,
    split_fields,
    template_variables,
)


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
    baidu = find_model("baidu-deepseek-v3.2")
    ark = find_model("deepseek-v4-flash")
    assert baidu is not None and ark is not None
    assert build_body(baidu, "hi", thinking=False)["thinking"] == {"type": "disabled"}
    assert build_body(baidu, "hi", thinking=True, previous_response_id="resp_1")["previous_response_id"] == "resp_1"
    ark_body = build_body(ark, "hi", thinking=False)
    assert ark_body["thinking"] == {"type": "enabled"} and ark_body["tools"][0]["type"] == "web_search"
    assert ark_body["model"].startswith("ep-") and ark_body["stream"] is True


def test_costs_use_per_thousand_token_prices_and_search_price() -> None:
    inference, search = calc_costs("deepseek-v4-flash", 2000, 1000, 3)
    assert inference == Decimal("0.007500")
    assert search == Decimal("0.012000")
    assert calc_costs("unknown", 1000, 1000, 1) == (Decimal(0), Decimal(0))
    assert model_display_name("unknown") == "unknown"


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
