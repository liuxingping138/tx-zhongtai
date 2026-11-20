"""爬虫监测同步：只读采集总表，按「网站名称 + 省份 + 地市」统计。

总表在 ShardingSphere 代理后面，整表 GROUP BY 跑不出来，但单个采集日聚合不到 1 秒。
所以按采集日分桶存到 `policy_crawler_site_daily`，每天整体替换（删数据、重复同步都不会
让累计量偏掉），再由它汇总出页面读的 `policy_crawler_sites`。

三种方式：
    python -m app.cli.sync_crawler                 # 日常：按入库时间水位找出被动过的采集日重算
    python -m app.cli.sync_crawler --backfill      # 首次：从总表最早采集日回填到今天，并建立水位
    python -m app.cli.sync_crawler --days 30       # 修复：固定重算最近 30 天，不动水位

回填中断后加 --skip-existing 续跑，已入库的采集日不再重查（当天和昨天仍重算）。

水位只看 create_time。爬虫方把旧数据标记删除（status=-1）不会改 create_time，
日常增量感知不到；需要时用 --days 做一次修复性重算。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from platform_common.clock import BEIJING
from sqlalchemy import CursorResult, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.crawler.application import crawler_status as status_history
from app.crawler.domain.models import CrawlerSiteDaily, CrawlerSyncRun
from app.crawler.domain.provinces import stored_province
from app.crawler.repositories.crawler_sites import SYNC_LOCK_KEY
from app.crawler.repositories.source import mysql_connect, retry_mysql_read

logger = logging.getLogger("policy.cli.sync_crawler")

# 入库时间由爬虫库时钟写入，长事务可能让稍早的时间戳晚于水位才可见，回退一段再查。
_WATERMARK_OVERLAP = timedelta(hours=2)

MODE_INCREMENTAL = "incremental"
MODE_BACKFILL = "backfill"
MODE_REPAIR = "repair"


@dataclass(frozen=True)
class SyncWindow:
    """一次同步要处理的范围：模式，修复天数，回填起点，是否跳过已入库的日期。"""

    mode: str
    days: int = 7
    since: date | None = None
    skip_existing: bool = False


def _source_time(value: datetime) -> datetime:
    """爬虫库 create_time 是不带时区的北京时间。"""

    return value.replace(tzinfo=BEIJING).astimezone(UTC)


@retry_mysql_read
def fetch_day(day: date, today: date) -> list[dict[str, Any]]:
    """单个采集日按网站聚合。发布日期只认 YYYY-MM-DD 开头且不晚于今天的值。"""

    table = get_settings().crawler_data_table
    sql = f"""
        SELECT TRIM(COALESCE(site_name, '')) AS site_name,
               TRIM(COALESCE(prov_name, '')) AS province_name,
               TRIM(COALESCE(city_name, '')) AS city_name,
               COUNT(*) AS row_count,
               MAX(create_time) AS last_created,
               MAX(CASE WHEN introduced_date LIKE '____-__-__%%' AND LEFT(introduced_date, 10) <= %s
                        THEN LEFT(introduced_date, 10) END) AS last_published
        FROM {table}
        WHERE collect_date = %s AND (status IS NULL OR status <> '-1')
        GROUP BY TRIM(COALESCE(site_name, '')), TRIM(COALESCE(prov_name, '')), TRIM(COALESCE(city_name, ''))
    """  # noqa: S608  表名经 Settings 校验为标识符，值走参数绑定
    with mysql_connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (today.isoformat(), day.isoformat()))
        rows = cast(list[dict[str, Any]], cur.fetchall())
    return merge_day_rows(day, rows)


def _published(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:  # 形如 2026-09-99 的脏值
        return None


def merge_day_rows(day: date, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按本地主键合并。MySQL 的排序规则可能与截断后的本地键不一致，合并后才能安全写入。

    省份为空的记作国央企、「国家」记作全国，与同名同地市的另一种写法合为一个网站。
    """

    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row["site_name"] or "")[:255],
            stored_province(row["province_name"])[:64],
            str(row["city_name"] or "")[:64],
        )
        created = _source_time(row["last_created"]) if row["last_created"] else None
        published = _published(row["last_published"])
        item = merged.get(key)
        if item is None:
            merged[key] = {
                "collect_date": day,
                "site_name": key[0],
                "province_name": key[1],
                "city_name": key[2],
                "row_count": int(row["row_count"] or 0),
                "last_created_at": created,
                "last_published_date": published,
            }
            continue
        item["row_count"] += int(row["row_count"] or 0)
        item["last_created_at"] = max(filter(None, (item["last_created_at"], created)), default=None)
        item["last_published_date"] = max(filter(None, (item["last_published_date"], published)), default=None)
    return list(merged.values())


@retry_mysql_read
def fetch_affected_days(since: datetime) -> tuple[dict[date, datetime], datetime | None]:
    """入库时间晚于 since 的数据落在哪些采集日、每天最后一条的入库时间，以及其中最大的入库时间。create_time 有索引。"""

    table = get_settings().crawler_data_table
    sql = f"""
        SELECT collect_date, MAX(create_time) AS max_created
        FROM {table}
        WHERE create_time > %s
        GROUP BY collect_date
    """  # noqa: S608  表名经 Settings 校验为标识符，值走参数绑定
    with mysql_connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (since.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S"),))
        rows = cast(list[dict[str, Any]], cur.fetchall())
    days = {
        row["collect_date"]: _source_time(row["max_created"])
        for row in rows
        if row["collect_date"] and row["max_created"]
    }
    return days, max(days.values()) if days else None


@retry_mysql_read
def fetch_source_bounds() -> tuple[date | None, datetime | None]:
    """总表最早采集日与最大入库时间，两者都走索引，毫秒级。"""

    table = get_settings().crawler_data_table
    with mysql_connect() as conn, conn.cursor() as cur:
        cur.execute(f"SELECT MIN(collect_date) AS first_day FROM {table}")  # noqa: S608  表名经 Settings 校验为标识符，值走参数绑定
        first_day = cast(dict[str, Any], cur.fetchone())["first_day"]
        cur.execute(f"SELECT MAX(create_time) AS max_created FROM {table}")  # noqa: S608  表名经 Settings 校验为标识符，值走参数绑定
        max_created = cast(dict[str, Any], cur.fetchone())["max_created"]
    return first_day, _source_time(max_created) if max_created else None


async def replace_day(session: AsyncSession, day: date, rows: list[dict[str, Any]]) -> int:
    """同一事务先删后写，当天在源头消失的网站也会跟着消失。"""

    await session.execute(delete(CrawlerSiteDaily).where(CrawlerSiteDaily.collect_date == day))
    if not rows:
        return 0
    now = datetime.now(UTC)
    for start in range(0, len(rows), 1000):
        await session.execute(
            insert(CrawlerSiteDaily).values([dict(row, synced_at=now) for row in rows[start : start + 1000]])
        )
    return len(rows)


_REBUILD_SITES = text(
    """
    WITH today AS (SELECT CAST(now() AT TIME ZONE 'Asia/Shanghai' AS date) AS d),
    agg AS (
        SELECT site_name, province_name, city_name,
               SUM(row_count) AS total_rows,
               MAX(last_created_at) AS last_created_at,
               MAX(last_published_date) AS last_published_date,
               COALESCE(CAST(MAX(last_created_at) AT TIME ZONE 'Asia/Shanghai' AS date), MAX(collect_date))
                   AS last_active_date
        FROM policy_crawler_site_daily
        GROUP BY site_name, province_name, city_name
    )
    INSERT INTO policy_crawler_sites (
        id, site_name, province_name, city_name, total_rows, last_created_at,
        last_published_date, stale_days, status, computed_at
    )
    SELECT gen_random_uuid(), a.site_name, a.province_name, a.city_name, a.total_rows, a.last_created_at,
           a.last_published_date, s.stale_days,
           CASE WHEN s.stale_days <= :normal_days THEN 'normal'
                WHEN s.stale_days <= :watch_days THEN 'watch'
                ELSE 'stale' END,
           now()
    FROM agg a
    CROSS JOIN today t
    CROSS JOIN LATERAL (SELECT GREATEST(t.d - a.last_active_date, 0) AS stale_days) s
    """
)


async def rebuild_sites(session: AsyncSession) -> int:
    settings = get_settings()
    await session.execute(text("DELETE FROM policy_crawler_sites"))
    result = cast(
        CursorResult[Any],
        await session.execute(
            _REBUILD_SITES,
            {"normal_days": settings.crawler_health_normal_days, "watch_days": settings.crawler_health_watch_days},
        ),
    )
    return int(result.rowcount or 0)


async def _last_watermark(session: AsyncSession) -> datetime | None:
    return await session.scalar(
        select(CrawlerSyncRun.watermark)
        .where(CrawlerSyncRun.status == "success", CrawlerSyncRun.watermark.is_not(None))
        .order_by(CrawlerSyncRun.started_at.desc())
        .limit(1)
    )


async def _unfinished_backfill_mark(session: AsyncSession, *, exclude_run_id: uuid.UUID | None) -> datetime | None:
    """上一次没跑完的回填在开始时记下的水位。续跑必须沿用它，否则中断期间入库到已完成日期的数据会漏掉。

    - 排除本次运行：本次批次在规划前已以 running、水位为空写入，不排除就永远取到它自己。
    - 从新到旧看，碰到成功的回填就停：更早的失败已被那次完整回填覆盖，沿用它只会让水位倒退。
    """

    stmt = (
        select(CrawlerSyncRun.status, CrawlerSyncRun.watermark)
        .where(CrawlerSyncRun.mode == MODE_BACKFILL)
        .order_by(CrawlerSyncRun.started_at.desc())
    )
    if exclude_run_id is not None:
        stmt = stmt.where(CrawlerSyncRun.id != exclude_run_id)
    for status, watermark in (await session.execute(stmt)).all():
        if status == "success":
            return None
        if watermark is not None:
            return cast(datetime, watermark)
    return None


async def _existing_days(session: AsyncSession, date_from: date, date_to: date) -> set[date]:
    result = await session.execute(
        select(CrawlerSiteDaily.collect_date)
        .distinct()
        .where(CrawlerSiteDaily.collect_date.between(date_from, date_to))
    )
    return set(result.scalars())


def _span(date_from: date, date_to: date) -> list[date]:
    return [date_to - timedelta(days=offset) for offset in range((date_to - date_from).days + 1)]


async def plan(
    session: AsyncSession, window: SyncWindow, *, today: date, current_run_id: uuid.UUID | None = None
) -> tuple[list[date], datetime | None]:
    """返回要重算的采集日（新到旧）和成功后要记录的水位；修复模式不动水位。"""

    mode, days, since, skip_existing = window.mode, window.days, window.since, window.skip_existing

    if mode == MODE_REPAIR:
        return _span(today - timedelta(days=days - 1), today), None

    if mode == MODE_BACKFILL:
        # 先取水位再回填：回填期间新入库的数据入库时间一定晚于它，下次日常增量会补上。
        first_day, mark = await asyncio.to_thread(fetch_source_bounds)
        if skip_existing:
            previous = await _unfinished_backfill_mark(session, exclude_run_id=current_run_id)
            if previous is not None and (mark is None or previous < mark):
                mark = previous
        date_from = since or first_day or today
        targets = _span(date_from, today)
        if skip_existing:
            done = await _existing_days(session, date_from, today) - {today, today - timedelta(days=1)}
            targets = [day for day in targets if day not in done]
        return targets, mark

    watermark = await _last_watermark(session)
    if watermark is None:
        raise RuntimeError("尚未建立同步水位，请先执行一次回填：make crawler-backfill")
    # 先结束读水位开的事务再去源库：代理后找受影响日期可能要几分钟，事务开着会撞空闲事务超时，
    # 被断开的正是持有同步会话锁（advisory lock）的那条连接。
    await session.commit()
    touched, mark = await asyncio.to_thread(fetch_affected_days, watermark - _WATERMARK_OVERLAP)
    # 水位只在整次成功后才往前走：补录了好几天、一次跑不完超时后，重试和第二天都会把同一批日期从头再算，
    # 单日聚合最长要七八分钟，「重日」一多就永远超时。上一次（失败的那次）已经在这一天最后一条入库之后
    # 重算过的日期跳过，每次重试都能往前推进。
    synced = await _synced_days(session, list(touched))
    fresh = {day for day, last_in in touched.items() if day not in synced or synced[day] < last_in + _WATERMARK_OVERLAP}
    # 当天数据还在写，无论水位怎么说都重算。水位没有新数据时保持原值。
    return sorted(fresh | {today}, reverse=True), mark or watermark


async def _synced_days(session: AsyncSession, days: list[date]) -> dict[date, datetime]:
    """这些采集日在本地是什么时候整天重算的（同一天的行同一时刻写入）。"""

    if not days:
        return {}
    result = await session.execute(
        select(CrawlerSiteDaily.collect_date, func.min(CrawlerSiteDaily.synced_at))
        .where(CrawlerSiteDaily.collect_date.in_(days))
        .group_by(CrawlerSiteDaily.collect_date)
    )
    return {row[0]: row[1] for row in result.all()}


async def _sync(session: AsyncSession, window: SyncWindow, *, run_id: uuid.UUID | None = None) -> None:
    mode = window.mode
    today = datetime.now(BEIJING).date()
    run_row = CrawlerSyncRun(
        id=run_id or uuid.uuid4(), mode=mode, started_at=datetime.now(UTC), status="running", days_synced=0, site_rows=0
    )
    session.add(run_row)
    await session.commit()

    try:
        targets, mark = await plan(session, window, today=today, current_run_id=run_row.id)
        run_row.date_from = min(targets) if targets else None
        run_row.date_to = max(targets) if targets else None
        if mode == MODE_BACKFILL:
            # 回填开始就记下水位，失败后 --skip-existing 续跑要沿用它；只有成功批次的水位会被日常增量采用。
            run_row.watermark = mark
        await session.commit()
        logger.info(
            "sync_planned mode=%s days=%s newest=%s oldest=%s", mode, len(targets), run_row.date_to, run_row.date_from
        )

        for index, day in enumerate(targets, start=1):
            rows = await asyncio.to_thread(fetch_day, day, today)
            await replace_day(session, day, rows)
            run_row.days_synced = index
            await session.commit()
            logger.info("day_synced date=%s sites=%s progress=%s/%s", day, len(rows), index, len(targets))

        run_row.site_rows = await rebuild_sites(session)
        await status_history.refresh_history(session, today)
        run_row.watermark = mark if mode != MODE_REPAIR else None
        run_row.status = "success"
        run_row.finished_at = datetime.now(UTC)
        await session.commit()
        logger.info("sites_rebuilt rows=%s", run_row.site_rows)
    except Exception as exc:
        await session.rollback()
        run_row.status = "failed"
        run_row.error_message = str(exc)[:2000]
        run_row.finished_at = datetime.now(UTC)
        await session.commit()
        raise


async def run(
    *, mode: str, days: int = 7, since: date | None = None, skip_existing: bool = False, run_id: uuid.UUID | None = None
) -> None:
    # 整次同步用同一连接持有会话锁：按日 commit 不释放锁，两次同步不会交错覆盖。
    async with engine.connect() as connection:
        locked = await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": SYNC_LOCK_KEY})
        await connection.commit()
        if not locked:
            raise RuntimeError("已有爬虫监测同步正在运行，请稍后重试")
        try:
            async with SessionLocal(bind=connection) as session:
                await _sync(
                    session, SyncWindow(mode=mode, days=days, since=since, skip_existing=skip_existing), run_id=run_id
                )
        finally:
            await connection.rollback()
            await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": SYNC_LOCK_KEY})
            await connection.commit()
