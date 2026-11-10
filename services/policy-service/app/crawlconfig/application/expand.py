"""把按栏目展开的计划（domain.expand）落到信源表。同步和预览共用：预览只算、不改。"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import datetime

from platform_common.actors import Actor
from sqlalchemy.ext.asyncio import AsyncSession

from app.crawlconfig.domain.expand import ADOPT, CONVERT, CREATE, ColumnRule, ExpandPlan, Step, plan_expansion
from app.crawlconfig.repositories import sources as repo
from app.policy.application.region import make_internal_id
from app.policy.domain.fields import CRAWLER_STATUS_ONLINE, CRAWLER_STATUS_PENDING
from app.policy.domain.models import SOURCE_FIELDS, Source

# 展开出来的行照抄网站那一行，只有这几列换成规则的。
_OWN_FIELDS = ("tag", "url", "crawler_status", "online_date")
INTERNAL_ID_TAKEN = "网站名称+省份+地市+栏目名和已有的信源重复"


@dataclass(frozen=True)
class Stamp:
    """谁、什么时候改的，以及上线时给历史已爬统一补填的日期（这天上线的不算真的配置日，早晚都对齐）。"""

    now: datetime
    actor: Actor
    placeholder: str = ""


@dataclass
class ExpandResult:
    plan: ExpandPlan
    # 展开后内部唯一 id 撞上已有的信源（同网站名、省、市，标签又正好一样），这条规则这次不展开。
    conflicts: list[tuple[Step, str]] = field(default_factory=list)
    # 展开以后爬虫同事改了网站编码的规则（规则, 已展开的那一行）：那一行留在原编码下照常跟着规则走，列出来让人核对。
    moved: list[tuple[ColumnRule, Source]] = field(default_factory=list)
    added: int = 0
    marked: list[str] = field(default_factory=list)
    redated: list[str] = field(default_factory=list)


def new_internal_id(step: Step) -> str:
    row = step.row
    return make_internal_id(row.site_name, row.province_name, row.city_name, step.rule.module)


async def _without_conflicts(session: AsyncSession, steps: list[Step]) -> tuple[list[Step], list[tuple[Step, str]]]:
    changing = [step for step in steps if step.kind != ADOPT]
    wanted = {step: new_internal_id(step) for step in changing}
    taken = await repo.taken_internal_ids(session, wanted.values())
    repeated = Counter(wanted.values())
    kept: list[Step] = []
    conflicts: list[tuple[Step, str]] = []
    dropped_converts: set[uuid.UUID] = set()
    for step in steps:
        internal_id = wanted.get(step)
        own = step.kind == CONVERT and step.row.internal_id == internal_id
        if internal_id is not None and not own and (internal_id in taken or repeated[internal_id] > 1):
            conflicts.append((step, INTERNAL_ID_TAKEN))
            if step.kind == CONVERT:
                dropped_converts.add(step.row.id)
        else:
            next_step = step
            if step.kind == CREATE and step.row.id in dropped_converts:
                dropped_converts.remove(step.row.id)
                next_step = Step(CONVERT, step.rule, step.row)
            kept.append(next_step)
    return kept, conflicts


def _settle(row: Source, rule: ColumnRule, result: ExpandResult, *, touched: bool, stamp: Stamp) -> None:
    """这一行就是这条规则：已爬、上线时间就是规则的创建日期。异常等人工状态不动。

    对齐口径和按网站一行的一样（repositories.sources.apply_rule_dates）：同步第一次见到规则时早晚都对齐；
    见过之后（rule_date 有值）只往前挪、不往后挪。网站改版后同事按原栏目名重建了规则（新 ID），
    已经算进某一周、汇报过的那一行不能挪到本周。
    """

    target = rule.day.isoformat()
    seen = row.rule_date
    row.rule_date = min(seen, target) if seen else target
    if row.crawler_status in (*CRAWLER_STATUS_PENDING, CRAWLER_STATUS_ONLINE):
        if row.crawler_status != CRAWLER_STATUS_ONLINE:
            row.crawler_status = CRAWLER_STATUS_ONLINE
            row.online_date = target
            result.marked.append(row.site_code)
            touched = True
        else:
            ruled = seen and row.online_date and row.online_date != stamp.placeholder
            if row.online_date != target and not (ruled and row.online_date < target):
                row.online_date = target
                result.redated.append(row.site_code)
                touched = True
    if touched:
        row.version += 1
        row.updated_at = stamp.now
        row.updated_by_id, row.updated_by_name = stamp.actor.id, stamp.actor.name


def _new_row(step: Step, *, now: datetime, actor: Actor) -> Source:
    template, rule = step.row, step.rule
    copied = {name: getattr(template, name) for name in SOURCE_FIELDS if name not in _OWN_FIELDS}
    keep_status = template.crawler_status not in (*CRAWLER_STATUS_PENDING, CRAWLER_STATUS_ONLINE)
    return Source(
        **copied,
        internal_id=new_internal_id(step),
        site_code=template.site_code,
        tag=rule.module,
        url=rule.link,
        crawler_status=template.crawler_status if keep_status else CRAWLER_STATUS_ONLINE,
        online_date=template.online_date if keep_status else rule.day.isoformat(),
        rule_date=rule.day.isoformat(),
        rule_id=rule.rule_id,
        version=1,
        created_at=now,
        created_by_id=actor.id,
        created_by_name=actor.name,
        updated_at=now,
        updated_by_id=actor.id,
        updated_by_name=actor.name,
    )


async def expand(
    session: AsyncSession,
    columns: list[ColumnRule],
    legacy_codes: Collection[str],
    stamp: Stamp,
    *,
    apply: bool = True,
) -> ExpandResult:
    """columns：展开那天起建的规则；legacy_codes：那天之前就有规则的网站编码。apply=False 只算计划（预览）。"""

    rows = await repo.site_rows(session, {rule.site_code for rule in columns}, {rule.rule_id for rule in columns})
    plan = plan_expansion(rows, columns, legacy_codes)
    steps, conflicts = await _without_conflicts(session, plan.steps)
    linked = {row.rule_id: row for row in rows if row.rule_id}
    moved = [(rule, row) for rule in columns if (row := linked.get(rule.rule_id)) and row.site_code != rule.site_code]
    result = ExpandResult(
        plan=ExpandPlan(steps=steps, unknown=plan.unknown, duplicates=plan.duplicates),
        conflicts=conflicts,
        moved=moved,
    )
    if not apply:
        return result
    # 已经展开过的行：规则还在，状态和日期跟着它（人工把已爬改回未爬的，下次同步会再标回来，和按网站一行时一样）。
    for rule in columns:
        if (row := linked.get(rule.rule_id)) is not None:
            _settle(row, rule, result, touched=False, stamp=stamp)
    for step in steps:
        if step.kind == CREATE:
            session.add(_new_row(step, now=stamp.now, actor=stamp.actor))
            result.added += 1
            continue
        row = step.row
        if step.kind == CONVERT:
            row.tag, row.url, row.internal_id = step.rule.module, step.rule.link, new_internal_id(step)
        row.rule_id = step.rule.rule_id
        _settle(row, step.rule, result, touched=True, stamp=stamp)
    return result
