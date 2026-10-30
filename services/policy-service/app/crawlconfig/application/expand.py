"""把按栏目展开的计划（domain.expand）落到信源表。同步和预览共用：预览只算、不改。"""

from __future__ import annotations

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


@dataclass
class ExpandResult:
    plan: ExpandPlan
    # 展开后内部唯一 id 撞上已有的信源（同网站名、省、市，标签又正好一样），这条规则这次不展开。
    conflicts: list[tuple[Step, str]] = field(default_factory=list)
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
    for step in steps:
        internal_id = wanted.get(step)
        own = step.kind == CONVERT and step.row.internal_id == internal_id
        if internal_id is not None and not own and (internal_id in taken or repeated[internal_id] > 1):
            conflicts.append((step, INTERNAL_ID_TAKEN))
        else:
            kept.append(step)
    return kept, conflicts


def _settle(row: Source, rule: ColumnRule, result: ExpandResult, *, touched: bool, now: datetime, actor: Actor) -> None:
    """这一行就是这条规则：已爬、上线时间就是规则的创建日期。异常等人工状态不动。"""

    target = rule.day.isoformat()
    row.rule_date = target
    if row.crawler_status in (*CRAWLER_STATUS_PENDING, CRAWLER_STATUS_ONLINE):
        if row.crawler_status != CRAWLER_STATUS_ONLINE:
            row.crawler_status = CRAWLER_STATUS_ONLINE
            result.marked.append(row.site_code)
            touched = True
        elif row.online_date != target:
            result.redated.append(row.site_code)
            touched = True
        row.online_date = target
    if touched:
        row.version += 1
        row.updated_at = now
        row.updated_by_id, row.updated_by_name = actor.id, actor.name


def _new_row(step: Step, *, now: datetime, actor: Actor) -> Source:
    template, rule = step.row, step.rule
    copied = {name: getattr(template, name) for name in SOURCE_FIELDS if name not in _OWN_FIELDS}
    return Source(
        **copied,
        internal_id=new_internal_id(step),
        site_code=template.site_code,
        tag=rule.module,
        url=rule.link,
        crawler_status=CRAWLER_STATUS_ONLINE,
        online_date=rule.day.isoformat(),
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
    *,
    now: datetime,
    actor: Actor,
    apply: bool = True,
) -> ExpandResult:
    """columns：展开那天起建的规则；legacy_codes：那天之前就有规则的网站编码。apply=False 只算计划（预览）。"""

    rows = await repo.site_rows(session, {rule.site_code for rule in columns})
    plan = plan_expansion(rows, columns, legacy_codes)
    steps, conflicts = await _without_conflicts(session, plan.steps)
    result = ExpandResult(plan=ExpandPlan(steps=steps, unknown=plan.unknown), conflicts=conflicts)
    if not apply:
        return result
    # 已经展开过的行：规则还在，状态和日期跟着它（人工把已爬改回未爬的，下次同步会再标回来，和按网站一行时一样）。
    linked = {row.rule_id: row for row in rows if row.rule_id}
    for rule in columns:
        if (row := linked.get(rule.rule_id)) is not None:
            _settle(row, rule, result, touched=False, now=now, actor=actor)
    for step in steps:
        if step.kind == CREATE:
            session.add(_new_row(step, now=now, actor=actor))
            result.added += 1
            continue
        row = step.row
        if step.kind == CONVERT:
            row.tag, row.url, row.internal_id = step.rule.module, step.rule.link, new_internal_id(step)
        row.rule_id = step.rule.rule_id
        _settle(row, step.rule, result, touched=True, now=now, actor=actor)
    return result
