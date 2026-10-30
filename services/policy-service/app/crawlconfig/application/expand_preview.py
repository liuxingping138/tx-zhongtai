"""信源按栏目展开的预览：从某天起建的规则会怎样落到信源表，写成 Excel 给人看，不改库。

正式展开走每天的爬虫配置同步（见 rules_sync）；第一次打开展开前先拿这张表核对。
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import date

from platform_common.actors import Actor
from platform_common.clock import utcnow
from platform_common.xlsx_writer import write_text_xlsx

from app.core.database import SessionLocal
from app.crawlconfig.application.expand import ExpandResult, Stamp, expand
from app.crawlconfig.domain.expand import ADOPT, CONVERT, ColumnRule, Step, page_key
from app.crawlconfig.repositories import rules_source
from app.crawlconfig.repositories import sources as repo
from app.policy.domain.models import Source

HEADERS = (
    "动作",
    "规则ID",
    "网站编码",
    "网站名称",
    "省份",
    "地市",
    "栏目名（新标签）",
    "链接",
    "规则创建日期",
    "原标签",
    "原链接",
    "说明",
)
ACTION_TEXT = {CONVERT: "原来那行改成这个栏目", ADOPT: "已有这个栏目的行，记上规则ID"}
CREATE_TEXT = "照抄网站那行新增一行"
_PREVIEW_ACTOR = Actor(id="preview", name="预览")


def _site_key(row: Source) -> tuple[str, str, str]:
    return row.site_name, row.province_name, row.city_name


def _possible_duplicate(step: Step, same_site: list[Source]) -> str:
    """同一个网站（名称、省、市都一样）里另一条信源的链接和这条规则的一样：可能是同一个栏目早就单独建过。"""

    link = page_key(step.rule.link)
    others = [row for row in same_site if row.id != step.row.id and link and page_key(row.url) == link]
    return "；".join(f"同网站已有相同链接的信源 {row.site_code}（标签：{row.tag[:40]}）" for row in others[:3])


def _step_line(step: Step, note: str, same_site: list[Source]) -> list[str]:
    row, rule = step.row, step.rule
    action = ACTION_TEXT.get(step.kind, CREATE_TEXT)
    original = (row.tag, row.url) if step.kind in ACTION_TEXT else ("", "")
    explain = note or _possible_duplicate(step, same_site)
    return [action, rule.rule_id, rule.site_code, row.site_name, row.province_name, row.city_name,
            rule.module, rule.link, rule.day.isoformat(), *original, explain]  # fmt: skip


def _unknown_line(rule: ColumnRule) -> list[str]:
    return ["不展开", rule.rule_id, rule.site_code, "", "", "", rule.module, rule.link, rule.day.isoformat(),
            "", "", "信源表里没有这个网站编码"]  # fmt: skip


def _duplicate_line(rule: ColumnRule, row: Source) -> list[str]:
    note = f"同一个网页已在网站编码 {row.site_code} 下对上规则（标签：{row.tag[:40]}），只算一个栏目"
    return ["不展开", rule.rule_id, rule.site_code, row.site_name, row.province_name, row.city_name, rule.module,
            rule.link, rule.day.isoformat(), "", "", note]  # fmt: skip


def _moved_line(rule: ColumnRule, row: Source) -> list[str]:
    note = f"已在网站编码 {row.site_code} 下展开过，规则后来改了编码：那一行留在原编码下，请核对"
    return ["不动", rule.rule_id, rule.site_code, row.site_name, row.province_name, row.city_name, rule.module,
            rule.link, rule.day.isoformat(), row.tag, row.url, note]  # fmt: skip


def _sheet(result: ExpandResult, sites: dict[tuple[str, str, str], list[Source]]) -> bytes:
    lines: list[list[str]] = [list(HEADERS)]
    lines.extend(_step_line(step, "", sites.get(_site_key(step.row), [])) for step in result.plan.steps)
    lines.extend(["不展开", *_step_line(step, reason, [])[1:]] for step, reason in result.conflicts)
    lines.extend(_unknown_line(rule) for rule in result.plan.unknown)
    lines.extend(_duplicate_line(rule, row) for rule, row in result.plan.duplicates)
    lines.extend(_moved_line(rule, row) for rule, row in result.moved)
    return write_text_xlsx("按栏目展开预览", lines, column_count=len(HEADERS))


async def preview(expand_from: date) -> tuple[bytes, dict[str, int]]:
    rules = await asyncio.to_thread(rules_source.read_rule_codes, expand_from)
    async with SessionLocal() as session:
        stamp = Stamp(now=utcnow(), actor=_PREVIEW_ACTOR)
        result = await expand(session, rules.columns, set(rules.first_dates), stamp, apply=False)
        names = {step.row.site_name for step in result.plan.steps}
        sites: dict[tuple[str, str, str], list[Source]] = {}
        for row in await repo.rows_of_sites(session, names):
            sites.setdefault(_site_key(row), []).append(row)
        # 表在会话里生成：回滚会让读出来的行全部过期，之后再取字段会报错。
        content = _sheet(result, sites)
        await session.rollback()
    counts = Counter(step.kind for step in result.plan.steps)
    summary = {
        "规则": len(rules.columns),
        "改原来那行": counts[CONVERT],
        "新增": counts["create"],
        "记上规则ID": counts[ADOPT],
        "撞上已有信源不展开": len(result.conflicts),
        "信源表没有这个编码": len(result.plan.unknown),
        "同一网页另一编码已有": len(result.plan.duplicates),
        "展开后改了网站编码": len(result.moved),
    }
    return content, summary
