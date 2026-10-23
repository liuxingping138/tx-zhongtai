"""爬虫配置统计：所选自然周的分省统计、近 12 周趋势和本周新增明细；导出同一份数据的 Excel。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from anyio import to_thread
from platform_common.actors import Actor
from platform_common.clock import BEIJING
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.audit_emit import enqueue_event
from app.core.config import get_settings
from app.crawlconfig.application import rules_sync
from app.crawlconfig.application.report_excel import build_report_workbook
from app.crawlconfig.domain import report as rules
from app.crawlconfig.repositories import report as repo
from app.policy.domain.models import Source

SITE_FIELDS = ("province_name", "city_name", "district_name", "site_name", "site_code", "url", "crawler_status")
COUNT_FIELDS = ("total", "online", "pending", "abnormal", "new")


def site_row(row: Source) -> dict[str, str]:
    return {**{key: getattr(row, key) for key in SITE_FIELDS}, "online_date": row.online_date}


def _province(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {key: int(row[key]) for key in COUNT_FIELDS}
    out["province_name"] = row["province_name"] or rules.BLANK_PROVINCE
    out["coverage"] = rules.coverage(out["online"], out["total"])
    return out


async def build_report(session: AsyncSession, week: date | None) -> dict[str, Any]:
    backfill = get_settings().crawler_config_backfill_date.isoformat()
    selected = rules.week_start(week or datetime.now(BEIJING).date())
    week_from, week_to = selected.isoformat(), rules.week_end(selected).isoformat()
    rows = sorted(await repo.province_rows(session, week_from, week_to, backfill), key=rules.province_order)
    provinces = [_province(row) for row in rows]
    totals: dict[str, Any] = {key: sum(row[key] for row in provinces) for key in COUNT_FIELDS}
    totals["coverage"] = rules.coverage(totals["online"], totals["total"])
    weeks = rules.trend_weeks(selected)
    baseline = await repo.count_baseline(session, backfill)
    trend = rules.weekly_series(await repo.online_by_day(session, week_to, backfill), weeks, baseline)
    daily_by_province = await repo.online_by_province_day(session, weeks[0].isoformat(), week_to, backfill)
    by_province = rules.province_weekly(daily_by_province, weeks)
    for row in provinces:
        # 每个省近 12 周（和 trend 同样的周）各配置了多少网站，最后一个就是所选这周。
        row["weekly"] = by_province.get(row["province_name"], [0] * len(weeks))
    new_sites = await repo.sites_online_between(session, week_from, week_to, backfill)
    return {
        "week_from": week_from,
        "week_to": week_to,
        "backfill_date": backfill,
        "baseline": baseline,
        "previous_new": trend[-2]["new"],
        "totals": totals,
        "provinces": provinces,
        "trend": trend,
        "new_sites": [site_row(row) for row in new_sites],
        "last_sync": await rules_sync.latest(session),
    }


async def export_report(session: AsyncSession, actor: Actor, week: date | None) -> tuple[bytes, str]:
    data = await build_report(session, week)
    abnormal = [site_row(row) for row in await repo.abnormal_sites(session)]
    content = await to_thread.run_sync(build_report_workbook, data, abnormal)
    await enqueue_event(
        session,
        event_type="policy.crawler_config.exported",
        actor=actor,
        target_id=data["week_from"],
        extra={"week_from": data["week_from"], "week_to": data["week_to"]},
    )
    return content, f"爬虫配置统计_{data['week_from']}至{data['week_to']}.xlsx"
