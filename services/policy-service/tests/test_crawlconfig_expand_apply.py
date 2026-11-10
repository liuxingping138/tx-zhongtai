"""展开计划落到信源表：上线时间怎么对齐、没展开的规则怎么记下来。仓储用替身，不连库。"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from platform_common.actors import Actor

from app.crawlconfig.application import expand as expand_app
from app.crawlconfig.domain.expand import ADOPT, ColumnRule
from app.crawlconfig.repositories import sources as repo
from app.policy.domain.models import Source

NOW = datetime(2026, 10, 30, tzinfo=UTC)
STAMP = expand_app.Stamp(now=NOW, actor=Actor(id="t", name="测试"), placeholder="2026-10-22")


def _row(code: str, tag: str, **values: Any) -> Source:
    defaults: dict[str, Any] = {"url": "", "rule_id": "", "crawler_status": "未爬", "online_date": "", "rule_date": ""}
    return Source(
        id=uuid.uuid4(),
        internal_id=uuid.uuid4().hex,
        site_code=code,
        site_name="某局",
        province_name="北京市",
        city_name="",
        tag=tag,
        version=1,
        created_at=NOW,
        **{**defaults, **values},
    )


@pytest.fixture
def rows(monkeypatch: pytest.MonkeyPatch) -> list[Source]:
    found: list[Source] = []

    async def site_rows(*_: object) -> list[Source]:
        return found

    async def taken(*_: object) -> set[str]:
        return set()

    monkeypatch.setattr(repo, "site_rows", site_rows)
    monkeypatch.setattr(repo, "taken_internal_ids", taken)
    return found


async def test_an_already_reported_row_is_not_moved_to_this_week(rows: list[Source]) -> None:
    """老网站只有一行、标签就是栏目名，同步见过规则、上线时间 2025-05-06 已经汇报过。同事改版后按原栏目名重建了规则：
    这行对上新规则，但上线时间只往前对齐、不往后挪，不能从那一周挪到本周（和按网站一行的对齐同一口径）。"""

    old = _row("11010100001", "政策法规", crawler_status="已爬", online_date="2025-05-06", rule_date="2025-05-06")
    rows.append(old)
    rule = ColumnRule("n1", "11010100001", "政策法规", "https://x.gov.cn/zcfg", date(2026, 10, 28))
    result = await expand_app.expand(None, [rule], {"11010100001"}, STAMP)  # type: ignore[arg-type]
    assert [step.kind for step in result.plan.steps] == [ADOPT]
    assert (old.rule_id, old.online_date, old.rule_date, result.redated) == ("n1", "2025-05-06", "2025-05-06", [])


async def test_a_row_seen_for_the_first_time_is_aligned_to_the_rule_date(rows: list[Source]) -> None:
    """同步第一次见到（rule_date 为空）：导入时随手填的、统一补填的上线时间都不是真的配置日，早晚都对齐。"""

    filled = _row("11010100002", "政策法规", crawler_status="已爬", online_date="2024-10-01")
    rows.append(filled)
    rule = ColumnRule("n2", "11010100002", "政策法规", "https://y.gov.cn/zcfg", date(2026, 10, 28))
    result = await expand_app.expand(None, [rule], set(), STAMP)  # type: ignore[arg-type]
    assert (filled.online_date, filled.rule_date, result.redated) == ("2026-10-28", "2026-10-28", ["11010100002"])


async def test_skipped_rules_are_kept_in_the_result(rows: list[Source]) -> None:
    """同一网页在另一编码下已对上、展开后改了编码的规则都留在结果里：预览和同步批次据此写出条数。"""

    page = "https://lyg.gov.cn/gfxwj.html"
    main = _row("32070000001", "政策|新闻", url="https://www.lyg.gov.cn")
    own = _row("32070000012", "规范性文件", url=page, rule_id="r_own", crawler_status="已爬")
    moved = _row("32070000013", "通知公告", rule_id="r_moved", crawler_status="已爬", online_date="2026-10-27")
    rows.extend([main, own, moved])
    columns = [
        ColumnRule("r_main", "32070000001", "政策_规范性文件", page, date(2026, 10, 30)),
        ColumnRule("r_moved", "32070000001", "通知公告", "https://lyg.gov.cn/tzgg", date(2026, 10, 27)),
    ]
    result = await expand_app.expand(None, columns, set(), STAMP, apply=False)  # type: ignore[arg-type]
    assert [rule.rule_id for rule, _ in result.plan.duplicates] == ["r_main"]
    assert [(rule.rule_id, row.site_code) for rule, row in result.moved] == [("r_moved", "32070000013")]


async def test_abnormal_site_expansion_keeps_abnormal_status(rows: list[Source]) -> None:
    """人工标成异常的网站展开多条栏目时，新建行也保持异常，不强行改成已爬。"""

    abn = _row("11010100009", "政策", crawler_status="异常", online_date="")
    rows.append(abn)
    c1 = ColumnRule("r1", "11010100009", "政策法规", "https://a.gov.cn/1", date(2026, 10, 28))
    c2 = ColumnRule("r2", "11010100009", "通知公告", "https://a.gov.cn/2", date(2026, 10, 29))
    added: list[Source] = []

    class Session:
        def add(self, row: Source) -> None:
            added.append(row)

    result = await expand_app.expand(Session(), [c1, c2], set(), STAMP)  # type: ignore[arg-type]
    assert result.added == 1
    assert abn.crawler_status == "异常"
    assert added[0].crawler_status == "异常" and added[0].online_date == ""
