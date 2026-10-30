"""信源按栏目展开：规则表一行一个栏目，从展开那天起每条规则在信源表里一行，只有标签和链接换成规则的。"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from app.crawlconfig.domain.expand import ADOPT, CONVERT, CREATE, ColumnRule, plan_expansion
from app.policy.domain.models import Source

NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _row(code: str, tag: str = "政策|新闻|通知公告", *, rule_id: str = "", minute: int = 0) -> Source:
    return Source(
        id=uuid.uuid4(),
        internal_id=uuid.uuid4().hex,
        site_code=code,
        site_name=f"网站{code}",
        province_name="江苏省",
        city_name="连云港市",
        tag=tag,
        rule_id=rule_id,
        created_at=NOW.replace(minute=minute),
    )


def _rule(rule_id: str, code: str, module: str, day: int = 30) -> ColumnRule:
    return ColumnRule(rule_id, code, module, f"https://a.gov.cn/{rule_id}", date(2026, 10, day))


def test_a_new_site_turns_its_row_into_the_first_column_and_adds_the_rest() -> None:
    """之前没有规则的网站：原来那行（标签里一串栏目）改成第一个栏目，其余栏目各新增一行。"""

    site = _row("32070000001")
    rules = [_rule("r2", "32070000001", "通知公告"), _rule("r1", "32070000001", "政策文件", day=29)]
    plan = plan_expansion([site], rules, legacy_codes=set())
    assert [(step.kind, step.rule.rule_id, step.row is site) for step in plan.steps] == [
        (CONVERT, "r1", True),
        (CREATE, "r2", True),
    ]


def test_a_site_with_earlier_rules_keeps_its_row_and_new_columns_are_added() -> None:
    """展开那天之前就配过规则的网站：原来那行代表之前配好的栏目，留着；新栏目另起一行。"""

    site = _row("11010100001")
    plan = plan_expansion([site], [_rule("r1", "11010100001", "政策文件")], legacy_codes={"11010100001"})
    assert [step.kind for step in plan.steps] == [CREATE]


def test_existing_column_rows_are_adopted_and_expanded_rules_are_not_expanded_again() -> None:
    site = _row("32070000001", minute=0)
    manual = _row("32070000001", "通知公告", minute=1)  # 人工已经按栏目建好的一行
    done = _row("32070000001", "政策文件", rule_id="r1", minute=2)
    rules = [_rule("r1", "32070000001", "政策文件"), _rule("r2", "32070000001", "通知公告")]
    plan = plan_expansion([site, manual, done], rules, legacy_codes=set())
    assert [(step.kind, step.rule.rule_id, step.row is manual) for step in plan.steps] == [(ADOPT, "r2", True)]
    # 已经有展开过的行：再来新栏目也不改原来那行，另起一行。
    plan = plan_expansion([site, done], [*rules, _rule("r3", "32070000001", "规划计划")], legacy_codes=set())
    assert [(step.kind, step.rule.rule_id) for step in plan.steps] == [(CREATE, "r2"), (CREATE, "r3")]


def test_rules_whose_site_code_is_not_in_sources_are_listed_as_unknown() -> None:
    plan = plan_expansion([], [_rule("r9", "99999999999", "政策")], legacy_codes=set())
    assert (plan.steps, [rule.rule_id for rule in plan.unknown]) == ([], ["r9"])


def test_a_row_already_named_after_a_column_is_matched_before_the_site_row_is_reused() -> None:
    """网站那行的标签正好是某条规则的栏目名：先对上它，其余栏目新增。

    原来先被别的栏目改掉，这条再新增时撞了内部唯一 id。"""

    site = _row("33100000099", "首页 <—> 政策法规 <—> 政策法规")
    rules = [
        _rule("a1", "33100000099", "政策法规_政策法规"),
        _rule("b2", "33100000099", "首页 <—> 政策法规 <—> 政策法规"),
    ]
    plan = plan_expansion([site], rules, legacy_codes=set())
    assert [(step.kind, step.rule.rule_id) for step in plan.steps] == [(CREATE, "a1"), (ADOPT, "b2")]


def test_the_same_page_under_another_site_code_counts_once() -> None:
    """同一个网页在两个网站编码下各配了一条规则，只算一个栏目（用户定的：链接相同的留一个）。

    删掉多出来的信源行后，规则表里的规则还在（规则表不归我们管），下次同步不能把它再展开回来。"""

    main = _row("32070000001")
    main.url = "https://www.lyg.gov.cn"
    own = _row("32070000012", "市政府规范性文件", rule_id="r_own", minute=1)
    own.url = "https://lyg.gov.cn/szfgfxwj1/szfgfxwj1.html"
    main.site_name = own.site_name = "连云港市人民政府"  # 同一个网站的两个网站编码
    rule = ColumnRule(
        "r_main",
        "32070000001",
        "政策_市政府规范性文件",
        "https://www.lyg.gov.cn/szfgfxwj1/szfgfxwj1.html/",
        date(2026, 10, 30),
    )
    plan = plan_expansion([main, own], [rule], legacy_codes=set())
    assert plan.steps == []
    assert [(item.rule_id, row.site_code) for item, row in plan.duplicates] == [("r_main", "32070000012")]

    # 两条都是新规则：先建的展开，后建的跳过。
    fresh = _row("32070000012", "市政府规范性文件", minute=1)
    fresh.url, fresh.site_name = own.url, own.site_name
    both = [_rule("a1", "32070000012", "市政府规范性文件"), _rule("b2", "32070000001", "政策_市政府规范性文件")]
    both[0] = ColumnRule("a1", "32070000012", "市政府规范性文件", own.url, date(2026, 10, 30))
    both[1] = ColumnRule("b2", "32070000001", "政策_市政府规范性文件", own.url, date(2026, 10, 30))
    plan = plan_expansion([main, fresh], both, legacy_codes=set())
    assert [step.rule.rule_id for step in plan.steps] == ["a1"]
    assert [item.rule_id for item, _ in plan.duplicates] == ["b2"]


def test_columns_sharing_one_address_under_the_same_code_still_count_separately() -> None:
    """常州那种：同一个网站编码下几个栏目共用一个接口地址，是不同的栏目，照常各算各的。"""

    site = _row("32040000001")
    shared = "https://www.changzhou.gov.cn/ns_class/zwgk_18?act=aj"
    rules = [
        ColumnRule("c1", "32040000001", "专项规划", shared, date(2026, 10, 30)),
        ColumnRule("c2", "32040000001", "质量监督", shared, date(2026, 10, 30)),
    ]
    plan = plan_expansion([site], rules, legacy_codes=set())
    assert [step.kind for step in plan.steps] == [CONVERT, CREATE]
    assert plan.duplicates == []
