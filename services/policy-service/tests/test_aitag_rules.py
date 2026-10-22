from __future__ import annotations

from datetime import date

from app.aitag.domain import rules

KNOWN = ["信息化建设类", "工业制造类", "资金扶持类", "科技创新类", "人才政策类", "产业政策类", "顶层规划类"]


def test_content_is_compacted_and_truncated_with_a_visible_marker() -> None:
    page = "第一条\r\n\r\n\r\n   第二条　　内容\t\t结束"
    assert rules.clean_content(page, 100) == "第一条\n 第二条 内容 结束"
    assert rules.clean_content("甲" * 10, 4) == "甲甲甲甲……（正文过长，以下省略）"
    assert rules.clean_content(None, 10) == ""
    # 0 = 全文照传，十几万字也不截。
    assert rules.clean_content("甲" * 150_000, 0) == "甲" * 150_000


def test_policy_types_accept_old_spellings_drop_duplicates_and_cap_at_five() -> None:
    answer = "信息化建设、工业制造类，信息化建设类；科技创新/资金扶持类 人才政策类、产业政策类、顶层规划类"
    types, unknown = rules.parse_policy_types(answer, KNOWN)
    assert types == ["信息化建设类", "工业制造类", "科技创新类", "资金扶持类", "人才政策类"]
    assert unknown == []
    assert rules.parse_policy_types("数字经济类、-、无", KNOWN) == ([], ["数字经济类"])


def test_outcome_explains_failures_in_the_remark() -> None:
    assert rules.tagging_outcome({"error": "限流", "items": []}, KNOWN) == ([], "AI 类型判断失败：限流")
    ok = {"error": "", "items": [{"政策类型名称": "信息化建设类、资金扶持类"}]}
    assert rules.tagging_outcome(ok, KNOWN) == (["信息化建设类", "资金扶持类"], "")
    partly = {"error": "", "items": [{"政策类型名称": "信息化建设类、数字经济"}]}
    assert rules.tagging_outcome(partly, KNOWN) == (["信息化建设类"], "AI 返回的类型不在码表里：数字经济")
    assert rules.tagging_outcome({"error": "", "items": [{"政策类型名称": "-"}]}, KNOWN) == (
        [],
        "AI 没有判断出政策类型",
    )


def test_only_informatization_policies_go_on_to_interpretation() -> None:
    row = {"name": "某市数字政府方案", "prov_id": "11", "prov_name": "北京市", "introduced_date": date(2026, 10, 1)}
    values = rules.base_tag_values(row, ["信息化建设类", "资金扶持类"], "")
    assert (values["policy_types"], values["need_interpret"], values["issued_at"]) == (
        "信息化建设类、资金扶持类",
        "是",
        "2026-10-01",
    )
    assert rules.base_tag_values(row, ["资金扶持类"], "")["need_interpret"] == "否"


def test_resume_point_stops_at_the_first_row_that_was_not_run() -> None:
    results = [{"error": ""}, {"error": "限流"}, {"error": "未执行（任务停止或中断）"}, {"error": ""}]
    assert rules.resume_point(results, "未执行") == 2
    assert rules.resume_point(results[:2], "未执行") == 2


def test_prompt_row_uses_the_column_names_templates_reference() -> None:
    row = rules.prompt_row({"content_id": "abc", "name": " 标题 "}, "正文", 100)
    assert list(row) == [rules.SOURCE_ID, *rules.PROMPT_COLUMNS]
    assert (row["源ID"], row["政策标题"], row["政策正文"]) == ("abc", "标题", "正文")
