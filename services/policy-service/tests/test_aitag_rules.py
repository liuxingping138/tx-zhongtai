from __future__ import annotations

from datetime import date

from app.aitag.domain import rules
from app.policy.domain.fields import AI_NOTE_TYPE_EMPTY

KNOWN = ["信息化建设类", "工业制造类", "资金扶持类", "科技创新类", "人才政策类", "产业政策类", "顶层规划类"]


def test_content_is_compacted_and_truncated_with_a_visible_marker() -> None:
    page = "第一条\r\n\r\n\r\n   第二条　　内容\t\t结束"
    assert rules.clean_content(page, 100) == "第一条\n第二条 内容 结束"
    assert rules.clean_content("甲" * 10, 4) == "甲甲甲甲……（正文过长，以下省略）"
    assert rules.clean_content(None, 10) == ""
    # 0 = 全文照传，十几万字也不截。
    assert rules.clean_content("甲" * 150_000, 0) == "甲" * 150_000


def test_web_page_source_is_turned_into_its_visible_text() -> None:
    """源库正文是整页网页源码：脚本、样式、网页头都不要，段落保留，一句话里的行内标签不拆行。"""

    page = (
        "<!DOCTYPE html><html><head><title>标题</title><style>.a{color:red}</style>"
        "<script>var x = 1;</script></head><body><div class='nav'>首页 &gt; 新闻</div>"
        "<p>新华社北京10月16日电 <strong>习近平</strong>致信祝贺&nbsp;湖南大学。</p>"
        "<p>第二段<br/>换行后</p><script>jQuery('.fjxz')</script><noscript>请开启脚本</noscript></body></html>"
    )
    assert rules.clean_content(page, 0) == "新华社北京10月16日电 习近平致信祝贺 湖南大学。\n第二段\n换行后"
    # 不像网页的文字（Excel 里贴的正文、带尖括号的公式）原样处理。
    assert rules.clean_content("指标 a<b 且 c>d", 0) == "指标 a<b 且 c>d"
    # 先提取再截断：截的是文字，不是源码。
    assert rules.clean_content("<html><body><p>" + "字" * 50 + "</p></body></html>", 10).startswith("字" * 10 + "……")


def test_site_navigation_header_and_footer_are_dropped() -> None:
    """导航、页头页脚多半不是语义标签，是 div.header、ul.gov_navu_main 这种名字：按名字里的词认出来去掉，正文不动。"""

    page = (
        "<html><body><div class='gov_headerNavBox'><ul><li>首页</li><li>政务公开</li></ul>"
        "<div class='hd'>嵌套的 <div>同名标签</div> 也算导航</div></div>"
        "<nav>站内导航</nav><div class='crumb js-crumb'>当前位置：首页 &gt; 要闻</div>"
        "<div class='article'><p>第一段：为推动产业数字化转型，现就有关事项通知如下。</p>"
        "<div class='navigation-free'>第二段：名字里的 navigation 不是导航这个词，不算。</div></div>"
        "<div class='footer_wrap'>版权所有 ICP 备案号</div></body></html>"
    )
    assert rules.clean_content(page, 0) == (
        "第一段：为推动产业数字化转型，现就有关事项通知如下。\n第二段：名字里的 navigation 不是导航这个词，不算。"
    )


def test_navigation_filter_falls_back_when_it_would_swallow_the_body() -> None:
    """去导航出岔子就退回整页文字，宁可多几行导航也不能丢正文：
    没闭合的导航块吞了后面的正文；正文外框的名字里碰巧带 header，最长的那段正文没了。"""

    body = "正文" * 50
    unclosed = f"<html><body><div class='header'>首页 | 登录<div><p>{body}</p></div></body></html>"
    assert rules.clean_content(unclosed, 0) == f"首页 | 登录\n{body}"
    misnamed = (
        f"<html><body><div class='top'>首页</div><div class='content-header-wrap'><p>{body}</p></div></body></html>"
    )
    assert rules.clean_content(misnamed, 0) == f"首页\n{body}"
    # 否定词开头的名字（没有面包屑时的正文外框）不当导航，正文照留。
    negated = (
        f"<html><body><div class='header'>首页</div><div class='no-breadNav-padd'><p>{body}</p></div></body></html>"
    )
    assert rules.clean_content(negated, 0) == body


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


def test_script_titles_keep_only_the_text_and_note_it() -> None:
    """爬虫把 document.write(...) 整句存成了标题：取出里面的文字给模型和基础标签，备注里注明；正常标题不动。"""

    raw = 'document.write("".length>0?"":"谢松调研三峡集团江苏区域工作")'
    assert rules.policy_title(raw) == ("谢松调研三峡集团江苏区域工作", True)
    assert rules.policy_title("document.write('<span>' + '关于印发某某办法的通知' + '</span>')") == (
        "关于印发某某办法的通知",
        True,
    )
    assert rules.policy_title(" 关于 document.write 的说明 ") == ("关于 document.write 的说明", False)
    assert rules.policy_title("document.write(title)") == ("document.write(title)", False)

    assert (
        rules.prompt_row({"content_id": "abc", "name": raw}, "正文", 100)["政策标题"] == "谢松调研三峡集团江苏区域工作"
    )
    values = rules.base_tag_values({"name": raw}, [], AI_NOTE_TYPE_EMPTY)
    assert values["policy_name"] == "谢松调研三峡集团江苏区域工作"
    assert values["remark"] == f"{AI_NOTE_TYPE_EMPTY}；{rules.TITLE_SCRIPT_NOTE}"
    assert rules.base_tag_values({"name": raw}, [], "")["remark"] == rules.TITLE_SCRIPT_NOTE
    assert rules.base_tag_values({"name": "正常标题"}, [], "")["remark"] == ""
