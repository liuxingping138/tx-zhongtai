"""规则表一行一个栏目，信源表也按栏目展开：从 expand_from 那天起建的规则，每条在信源表里有一行。

用户的口径：工作量就是栏目数，规则表加了多少条，信源表就跟着多出多少行。规则用网站编码关联信源表里这个网站的行，
展开出来的行只有标签（栏目名）和链接换成规则的，其余字段照抄网站那一行；网站编码不变，同一个网站的几行共用。
每行记下对应的规则 ID，同一条规则不会展开两次，栏目名后来改了也还对得上。

这里只决定每条规则落到哪一行（纯计算，不碰库）。之前建的规则不展开，仍按网站一行（用户定的：历史不好处理，先不处理）。
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import date

from app.policy.domain.models import Source

# 网站原来那一行（标签里列着一串栏目）改成它的第一个栏目：这个网站之前没有规则时才这样，
# 有过规则的网站，原来那行代表之前配好的那些栏目，留着，新栏目另起一行。
CONVERT = "convert"
# 照抄这个网站的行新增一行。
CREATE = "create"
# 信源表里已经有这个栏目（同网站编码、标签就是栏目名）、还没记规则 ID 的行，记上就行。
ADOPT = "adopt"


@dataclass(frozen=True)
class ColumnRule:
    rule_id: str
    site_code: str
    module: str
    link: str
    day: date


@dataclass(frozen=True)
class Step:
    kind: str
    rule: ColumnRule
    # convert / adopt：要改的那一行；create：照抄的那一行。
    row: Source


@dataclass
class ExpandPlan:
    steps: list[Step] = field(default_factory=list)
    # 信源表里没有这个网站编码，展开不了。
    unknown: list[ColumnRule] = field(default_factory=list)
    # 同一个网页在两个网站编码下各配了一条规则：只展开先建的那条，这些不展开（规则, 已经对上的那一行）。
    duplicates: list[tuple[ColumnRule, Source]] = field(default_factory=list)


def page_key(url: str) -> str:
    """比较两个链接是不是同一个网页：不分 http/https、有没有 www.、结尾斜杠。"""

    text = (url or "").strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")
    return text.rstrip("/")


def _site(row: Source) -> tuple[str, str, str]:
    return row.site_name, row.province_name, row.city_name


def plan_expansion(rows: Sequence[Source], rules: Sequence[ColumnRule], legacy_codes: Collection[str]) -> ExpandPlan:
    """rows：这些规则涉及的网站编码在信源表里的全部行。legacy_codes：expand_from 之前就有规则的网站编码。"""

    linked = {row.rule_id for row in rows if row.rule_id}
    by_code: dict[str, list[Source]] = defaultdict(list)
    for row in sorted(rows, key=lambda item: (item.created_at, str(item.id))):
        by_code[row.site_code].append(row)
    pending = [rule for rule in sorted(rules, key=lambda item: (item.day, item.rule_id)) if rule.rule_id not in linked]
    plan = ExpandPlan(unknown=[rule for rule in pending if rule.site_code not in by_code])
    pending = [rule for rule in pending if rule.site_code in by_code]
    # 先把标签就是栏目名的行对上：不然原来那行可能先被别的栏目改掉，这条再新增时和它原来的内部唯一 id 撞上。
    taken: set[uuid.UUID] = set()
    adopted: dict[str, Step] = {}
    for rule in pending:
        same = next((row for row in _free(by_code[rule.site_code], taken) if row.tag.strip() == rule.module), None)
        if same is not None:
            adopted[rule.rule_id] = Step(ADOPT, rule, same)
            taken.add(same.id)
    # 同一网站里已经对上规则的网页（网站, 网页 -> 那一行）。同一个网页又挂在另一个网站编码下配了一条规则时，
    # 只算一个栏目（用户定的：链接相同的留一个）。同一个编码下几个栏目共用一个接口地址的（常州那种）照常各算各的。
    pages = {(_site(row), page_key(row.url)): row for row in rows if row.rule_id and page_key(row.url)}
    for rule in pending:
        step = adopted.get(rule.rule_id) or _place(rule, by_code[rule.site_code], taken, legacy_codes)
        page = (_site(step.row), page_key(rule.link))
        same = pages.get(page) if page[1] else None
        if same is not None and same.site_code != rule.site_code and step.kind != ADOPT:
            plan.duplicates.append((rule, same))
            continue
        if step.kind == CONVERT:
            taken.add(step.row.id)
        if page[1]:
            pages.setdefault(page, _planned(step))
        plan.steps.append(step)
    return plan


def _planned(step: Step) -> Source:
    """这一步做完后对上规则的那一行：新增的行还不存在，用照抄的那行带上新链接代替（只用来比较网站和网页）。"""

    if step.kind != CREATE:
        return step.row
    template = step.row
    return Source(
        site_code=template.site_code,
        site_name=template.site_name,
        province_name=template.province_name,
        city_name=template.city_name,
        url=step.rule.link,
        rule_id=step.rule.rule_id,
    )


def _free(site_rows: list[Source], taken: set[uuid.UUID]) -> list[Source]:
    return [row for row in site_rows if not row.rule_id and row.id not in taken]


def _place(rule: ColumnRule, site_rows: list[Source], taken: set[uuid.UUID], legacy_codes: Collection[str]) -> Step:
    """没有现成的栏目行：网站之前没有规则、也还没有行对上规则的，原来那行改成这个栏目；否则照抄新增。"""

    free = _free(site_rows, taken)
    started = any(row.rule_id or row.id in taken for row in site_rows)
    if free and rule.site_code not in legacy_codes and not started:
        return Step(CONVERT, rule, free[0])
    return Step(CREATE, rule, site_rows[0])
