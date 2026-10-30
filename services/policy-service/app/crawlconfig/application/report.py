"""爬虫配置统计：所选一期（周、月、季度、年）各省配置了多少网站、配置明细，各期柱图，以及信源表按省的爬虫状态透视；
导出同一份数据的 Excel。"""

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

# 按栏目展开后同一网站有好几行，只差栏目名（标签）和链接：明细要带上栏目名，不然看着像重复。
SITE_FIELDS = ("province_name", "city_name", "district_name", "site_name", "site_code", "tag", "url", "crawler_status")
STATUS_FIELDS = ("total", "online", "pending", "abnormal")


def site_row(row: Source) -> dict[str, str]:
    return {**{key: getattr(row, key) for key in SITE_FIELDS}, "online_date": row.online_date}


async def build_report(session: AsyncSession, unit: rules.Unit, period: date | None) -> dict[str, Any]:
    backfill = get_settings().crawler_config_backfill_date.isoformat()
    today = datetime.now(BEIJING).date()
    start = rules.period_start(period, unit) if period else rules.default_period(today, unit)
    end = rules.period_end(start, unit)
    previous = rules.shift(start, unit, -1)
    daily = await repo.online_by_day(session, backfill)
    rows = sorted(
        await repo.province_rows(session, start.isoformat(), end.isoformat(), backfill), key=rules.province_order
    )
    status = [
        {"province_name": row["province_name"] or rules.BLANK_PROVINCE, **{key: int(row[key]) for key in STATUS_FIELDS}}
        for row in rows
    ]
    # 这期有配置的省份才列，按数量从多到少：几个省有就是几个。
    configured: list[dict[str, Any]] = [
        {"province_name": row["province_name"] or rules.BLANK_PROVINCE, "new": int(row["new"])}
        for row in sorted(rows, key=lambda row: -int(row["new"]))
        if row["new"]
    ]
    totals: dict[str, Any] = {key: sum(row[key] for row in status) for key in STATUS_FIELDS}
    totals["coverage"] = rules.coverage(totals["online"], totals["total"])
    new_sites = await repo.sites_online_between(session, start.isoformat(), end.isoformat(), backfill)
    return {
        "unit": unit,
        "period_from": start.isoformat(),
        "period_to": end.isoformat(),
        "current_from": rules.period_start(today, unit).isoformat(),
        "new": sum(row["new"] for row in configured),
        "previous_new": rules.count_between(daily, previous, rules.period_end(previous, unit)),
        "periods": rules.series(daily, rules.window(today, unit, rules.earliest(daily)), unit),
        "provinces": configured,
        "status": status,
        "totals": totals,
        "backfill_date": backfill,
        "baseline": await repo.count_baseline(session, backfill),
        "new_sites": [site_row(row) for row in new_sites],
        "last_sync": await rules_sync.latest(session),
    }


async def export_report(
    session: AsyncSession, actor: Actor, unit: rules.Unit, period: date | None
) -> tuple[bytes, str]:
    data = await build_report(session, unit, period)
    abnormal = [site_row(row) for row in await repo.abnormal_sites(session)]
    content = await to_thread.run_sync(build_report_workbook, data, abnormal)
    await enqueue_event(
        session,
        event_type="policy.crawler_config.exported",
        actor=actor,
        target_id=data["period_from"],
        extra={"unit": unit, "period_from": data["period_from"], "period_to": data["period_to"]},
    )
    return content, f"爬虫配置统计_{data['period_from']}至{data['period_to']}.xlsx"
