"""把爬虫库的采集量按天聚合到本服务库，供爬虫监测页查询。

爬虫库是 400 万行的 MySQL（前面还挂着 ShardingSphere 代理），实测整表
`GROUP BY (网站,标签)` 跑十分钟都出不来，而单天聚合只要 1.4 秒。所以这里一律
按天分片查，页面永远只读本服务库里聚合好的小表。

按采集日（collect_date）分桶，但用入库时间（create_time）决定重算哪些天：
爬虫是采集完才入库，两者能差好几天且没有保证上限，固定天数窗口一旦小于实际滞后，
迟到的行进库时窗口已经滑过它的采集日，那天就永久少算。

用法：
    uv run python -m app.cli.sync_crawler                     # 日常增量，按入库时间水位决定重算范围
    uv run python -m app.cli.sync_crawler --since 2023-10-18  # 回填到指定日期
    uv run python -m app.cli.sync_crawler --days 30           # 强制固定回算 30 天
    uv run python -m app.cli.sync_crawler --tasks-only        # 只同步任务基线
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

import pymysql
from sqlalchemy import CursorResult, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domain.models import CrawlerDailyStat, CrawlerSyncRun, CrawlerTask

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("policy.cli.sync_crawler")

settings = get_settings()

# 水位回退量：入库时间由数据库时钟写入，长事务可能让稍早的时间戳晚于水位才可见。
_WATERMARK_OVERLAP_HOURS = 2


def _text_value(value: Any, limit: int) -> str:
    """规则 JSON 里同一个键可能是字符串也可能是数字（如 author），统一成字符串。"""

    if value is None:
        return ""
    return str(value).strip()[:limit]


def _mysql_connect() -> pymysql.connections.Connection:
    if not settings.crawler_mysql_host:
        raise RuntimeError("未配置 POLICY_CRAWLER_MYSQL_HOST，无法同步爬虫数据")
    return pymysql.connect(
        host=settings.crawler_mysql_host,
        port=settings.crawler_mysql_port,
        user=settings.crawler_mysql_user,
        password=settings.crawler_mysql_password,
        database=settings.crawler_mysql_db,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=30,
        read_timeout=600,
    )


def _fetch_rules() -> list[dict[str, Any]]:
    """读爬虫规则表。规则正文是 JSON 字符串，网站/标签都在 necessary_files 里。"""

    sql = f"SELECT id, correlation, state, rule FROM {settings.crawler_rules_table}"  # noqa: S608
    with _mysql_connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = cast(list[dict[str, Any]], cur.fetchall())

    tasks: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        raw = row.get("rule")
        if not raw:
            skipped += 1
            continue
        try:
            payload = json.loads(raw)
            need = payload.get("necessary_files") or {}
        except (ValueError, AttributeError):
            skipped += 1
            continue
        correlation = _text_value(row.get("correlation"), 64)
        if not correlation:
            skipped += 1
            continue
        tasks.append(
            {
                "correlation": correlation,
                "site_code": _text_value(need.get("author"), 100),
                "site_name": _text_value(need.get("site_name"), 255),
                "province_name": _text_value(need.get("prov_name"), 64),
                "city_name": _text_value(need.get("city_name"), 64),
                "tag": _text_value(need.get("tag"), 255),
                "source_url": _text_value(need.get("source_url"), 2000),
                "rule_state": int(row.get("state") or 0),
            }
        )
    logger.info("rules_fetched total=%s usable=%s skipped=%s", len(rows), len(tasks), skipped)
    return tasks


def _fetch_day(day: date) -> list[dict[str, Any]]:
    """单天按 (网站编码, 标签) 聚合。collect_date 上有索引，这条查询很快。"""

    sql = f"""
        SELECT COALESCE(author, '') AS site_code,
               COALESCE(tag, '') AS tag,
               MAX(site_name) AS site_name,
               MAX(prov_name) AS province_name,
               MAX(city_name) AS city_name,
               COUNT(*) AS row_count,
               SUM(name IS NOT NULL AND name <> '') AS named_count,
               SUM(content IS NOT NULL AND content <> '') AS content_count
        FROM {settings.crawler_data_table}
        WHERE collect_date = %s
        GROUP BY COALESCE(author, ''), COALESCE(tag, '')
    """  # noqa: S608
    with _mysql_connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (day.isoformat(),))
        rows = cast(list[dict[str, Any]], cur.fetchall())

    return [
        {
            "collect_date": day,
            "site_code": (row["site_code"] or "")[:100],
            "site_name": (row["site_name"] or "")[:255],
            "province_name": (row["province_name"] or "")[:64],
            "city_name": (row["city_name"] or "")[:64],
            "tag": (row["tag"] or "")[:255],
            "row_count": int(row["row_count"] or 0),
            "named_count": int(row["named_count"] or 0),
            "content_count": int(row["content_count"] or 0),
        }
        for row in rows
    ]


async def _upsert_tasks(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    now = datetime.now(UTC)
    written = 0
    for chunk_start in range(0, len(rows), 1000):
        chunk = [dict(row, synced_at=now) for row in rows[chunk_start : chunk_start + 1000]]
        stmt = insert(CrawlerTask).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[CrawlerTask.correlation],
            set_={
                "site_code": stmt.excluded.site_code,
                "site_name": stmt.excluded.site_name,
                "province_name": stmt.excluded.province_name,
                "city_name": stmt.excluded.city_name,
                "tag": stmt.excluded.tag,
                "source_url": stmt.excluded.source_url,
                "rule_state": stmt.excluded.rule_state,
                "synced_at": stmt.excluded.synced_at,
            },
        )
        await session.execute(stmt)
        written += len(chunk)
    return written


async def _upsert_daily(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    now = datetime.now(UTC)
    written = 0
    for chunk_start in range(0, len(rows), 1000):
        chunk = [dict(row, synced_at=now) for row in rows[chunk_start : chunk_start + 1000]]
        stmt = insert(CrawlerDailyStat).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[CrawlerDailyStat.collect_date, CrawlerDailyStat.site_code, CrawlerDailyStat.tag],
            set_={
                "site_name": stmt.excluded.site_name,
                "province_name": stmt.excluded.province_name,
                "city_name": stmt.excluded.city_name,
                "row_count": stmt.excluded.row_count,
                "named_count": stmt.excluded.named_count,
                "content_count": stmt.excluded.content_count,
                "synced_at": stmt.excluded.synced_at,
            },
        )
        await session.execute(stmt)
        written += len(chunk)
    return written


# 健康快照整体重算：本地 PG 上几万行，秒级完成，不值得做增量。
_RECOMPUTE_HEALTH = text(
    """
    WITH agg AS (
        SELECT site_code,
               tag,
               MAX(collect_date) AS last_collect_date,
               COALESCE(SUM(row_count) FILTER (WHERE collect_date > CURRENT_DATE - 7), 0) AS count_7d,
               COALESCE(SUM(row_count) FILTER (WHERE collect_date > CURRENT_DATE - 30), 0) AS count_30d,
               COALESCE(SUM(row_count) FILTER (WHERE collect_date > CURRENT_DATE - 90), 0) AS count_90d,
               COALESCE(SUM(row_count), 0) AS count_total,
               (ARRAY_AGG(site_name ORDER BY collect_date DESC))[1] AS site_name,
               (ARRAY_AGG(province_name ORDER BY collect_date DESC))[1] AS province_name,
               (ARRAY_AGG(city_name ORDER BY collect_date DESC))[1] AS city_name
        FROM policy_crawler_daily_stats
        GROUP BY site_code, tag
    ),
    tasks AS (
        SELECT DISTINCT ON (site_code, tag)
               site_code, tag, site_name, province_name, city_name, source_url
        FROM policy_crawler_tasks
        ORDER BY site_code, tag, synced_at DESC
    ),
    keys AS (
        SELECT site_code, tag FROM agg
        UNION
        SELECT site_code, tag FROM tasks
    )
    INSERT INTO policy_crawler_task_health (
        id, site_code, site_name, province_name, city_name, tag, source_url,
        last_collect_date, stale_days, count_7d, count_30d, count_90d, count_total,
        health_status, in_rules, computed_at
    )
    SELECT gen_random_uuid(),
           k.site_code,
           COALESCE(NULLIF(t.site_name, ''), a.site_name, ''),
           COALESCE(NULLIF(t.province_name, ''), a.province_name, ''),
           COALESCE(NULLIF(t.city_name, ''), a.city_name, ''),
           k.tag,
           COALESCE(t.source_url, ''),
           a.last_collect_date,
           CASE WHEN a.last_collect_date IS NULL THEN NULL ELSE CURRENT_DATE - a.last_collect_date END,
           COALESCE(a.count_7d, 0),
           COALESCE(a.count_30d, 0),
           COALESCE(a.count_90d, 0),
           COALESCE(a.count_total, 0),
           CASE
               WHEN a.last_collect_date IS NULL THEN 'never'
               WHEN CURRENT_DATE - a.last_collect_date <= :normal_days THEN 'normal'
               WHEN CURRENT_DATE - a.last_collect_date <= :watch_days THEN 'watch'
               ELSE 'broken'
           END,
           t.site_code IS NOT NULL,
           NOW()
    FROM keys k
    LEFT JOIN agg a ON a.site_code = k.site_code AND a.tag = k.tag
    LEFT JOIN tasks t ON t.site_code = k.site_code AND t.tag = k.tag
    ON CONFLICT (site_code, tag) DO UPDATE SET
        site_name = EXCLUDED.site_name,
        province_name = EXCLUDED.province_name,
        city_name = EXCLUDED.city_name,
        source_url = EXCLUDED.source_url,
        last_collect_date = EXCLUDED.last_collect_date,
        stale_days = EXCLUDED.stale_days,
        count_7d = EXCLUDED.count_7d,
        count_30d = EXCLUDED.count_30d,
        count_90d = EXCLUDED.count_90d,
        count_total = EXCLUDED.count_total,
        health_status = EXCLUDED.health_status,
        in_rules = EXCLUDED.in_rules,
        computed_at = EXCLUDED.computed_at
    """
)


async def recompute_health(session: AsyncSession) -> int:
    # execute() 的静态类型是 Result，INSERT 实际拿到的是带 rowcount 的 CursorResult。
    result = cast(
        CursorResult[Any],
        await session.execute(
            _RECOMPUTE_HEALTH,
            {"normal_days": settings.crawler_health_normal_days, "watch_days": settings.crawler_health_watch_days},
        ),
    )
    return int(result.rowcount or 0)


def _affected_days(since_ts: datetime) -> tuple[set[date], datetime | None]:
    """找出「入库时间晚于水位」的行涉及哪些采集日，以及本次见到的最大入库时间。

    爬虫是采集后才入库，两者能差好几天且没有保证上限。固定天数窗口一旦小于实际滞后，
    迟到的行进库时窗口已经滑过它的采集日，那天就永久少算。改成按入库时间反查采集日，
    不管滞后多久都能把对应的那天捞回来重算。
    """

    sql = f"""
        SELECT collect_date, MAX(create_time) AS max_created
        FROM {settings.crawler_data_table}
        WHERE create_time > %s AND collect_date IS NOT NULL
        GROUP BY collect_date
    """  # noqa: S608
    with _mysql_connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (since_ts.strftime("%Y-%m-%d %H:%M:%S"),))
        rows = cast(list[dict[str, Any]], cur.fetchall())

    days = {row["collect_date"] for row in rows if row["collect_date"]}
    stamps = [row["max_created"] for row in rows if row["max_created"]]
    return days, max(stamps) if stamps else None


async def _last_watermark(session: AsyncSession) -> datetime | None:
    result = await session.execute(
        text(
            "SELECT watermark FROM policy_crawler_sync_runs "
            "WHERE status = 'success' AND watermark IS NOT NULL "
            "ORDER BY started_at DESC LIMIT 1"
        )
    )
    return result.scalar_one_or_none()


async def _existing_days(session: AsyncSession, date_from: date, date_to: date) -> set[date]:
    result = await session.execute(
        text(
            "SELECT DISTINCT collect_date FROM policy_crawler_daily_stats "
            "WHERE collect_date BETWEEN :date_from AND :date_to"
        ),
        {"date_from": date_from, "date_to": date_to},
    )
    return {row[0] for row in result}


async def _days_to_sync(
    session: AsyncSession, *, today: date, days: int, since: date | None, use_watermark: bool
) -> tuple[list[date], datetime | None]:
    """决定这次要重算哪些采集日，以及本次的新水位。

    默认走水位：按入库时间反查被动过的采集日，滞后多久都不会漏。
    `--since` / `--days` 是人工指定的固定区间，回填和排查用。
    """

    if since is not None or not use_watermark:
        date_from = since if since else today - timedelta(days=days - 1)
        return [today - timedelta(days=offset) for offset in range((today - date_from).days + 1)], None

    watermark = await _last_watermark(session)
    if watermark is None:
        # 没有历史水位（首次运行），退回固定窗口，并在本次结束时建立水位。
        date_from = today - timedelta(days=days - 1)
        window = [today - timedelta(days=offset) for offset in range(days)]
        logger.info("watermark_missing fallback_from=%s", date_from)
        touched, new_mark = await asyncio.to_thread(
            _affected_days, datetime.combine(date_from, datetime.min.time(), tzinfo=UTC)
        )
        return sorted(set(window) | touched, reverse=True), new_mark

    # 回退一点再查：入库时间由数据库时钟写入，长事务可能让稍早的时间戳晚于水位才可见。
    probe_from = watermark - timedelta(hours=_WATERMARK_OVERLAP_HOURS)
    touched, new_mark = await asyncio.to_thread(_affected_days, probe_from)
    # 当天数据还在写，无论水位怎么说都要重算。
    return sorted(touched | {today}, reverse=True), new_mark


async def run(
    days: int,
    tasks_only: bool,
    since: date | None = None,
    skip_existing: bool = False,
    use_watermark: bool = True,
) -> None:
    today = date.today()
    started = datetime.now(UTC)

    async with SessionLocal() as session:
        targets, new_watermark = await _days_to_sync(
            session, today=today, days=days, since=since, use_watermark=use_watermark
        )
        date_from = min(targets) if targets else today
        run_row = CrawlerSyncRun(
            started_at=started, date_from=date_from, date_to=today, status="running"
        )
        session.add(run_row)
        await session.commit()

        try:
            task_rows = await _upsert_tasks(session, await asyncio.to_thread(_fetch_rules))
            await session.commit()
            logger.info("tasks_synced rows=%s", task_rows)

            stat_rows = 0
            if not tasks_only:
                # 长回填中途失败时用 --skip-existing 续跑，不必把已入库的日子再查一遍。
                # 当天和昨天永远重算：当天数据还在写，昨天可能补录。
                done = await _existing_days(session, date_from, today) if skip_existing else set()
                always_redo = {today, today - timedelta(days=1)}
                logger.info("days_to_sync count=%s newest=%s oldest=%s", len(targets), today, date_from)
                for day in targets:
                    if day in done and day not in always_redo:
                        continue
                    rows = await asyncio.to_thread(_fetch_day, day)
                    stat_rows += await _upsert_daily(session, rows)
                    await session.commit()
                    logger.info("day_synced date=%s groups=%s", day, len(rows))

            health_rows = await recompute_health(session)
            logger.info("health_recomputed rows=%s", health_rows)

            run_row.task_rows = task_rows
            run_row.stat_rows = stat_rows
            run_row.health_rows = health_rows
            run_row.status = "success"
            run_row.finished_at = datetime.now(UTC)
            # 水位只在真正跑完统计后前移；tasks-only 不动它，否则会跳过没算过的日子。
            if new_watermark is not None and not tasks_only:
                run_row.watermark = new_watermark
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            run_row.status = "failed"
            run_row.error_message = str(exc)[:2000]
            run_row.finished_at = datetime.now(UTC)
            session.add(run_row)
            await session.commit()
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="同步爬虫采集量到政策库")
    parser.add_argument(
        "--days",
        type=int,
        default=settings.crawler_sync_days,
        help="强制回算最近多少天（跳过水位判断）。默认按入库时间水位决定重算哪些采集日",
    )
    parser.add_argument(
        "--since",
        type=date.fromisoformat,
        default=None,
        help="从指定日期回填到今天（YYYY-MM-DD），优先于 --days。首次建议用爬虫库最早的采集日期，"
        "否则窗口外停更的任务会被算成「从未出数」。",
    )
    parser.add_argument("--tasks-only", action="store_true", help="只同步任务基线，不拉按天统计")
    parser.add_argument(
        "--fixed-window",
        action="store_true",
        help="不走入库时间水位，改为固定回算 --days 天（排查用）",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="跳过库里已有的日期，用于长回填中途失败后续跑；当天和昨天仍会重算",
    )
    args = parser.parse_args()
    asyncio.run(
        run(
            days=max(args.days, 1),
            tasks_only=args.tasks_only,
            since=args.since,
            skip_existing=args.skip_existing,
            use_watermark=not args.fixed_window,
        )
    )


if __name__ == "__main__":
    main()
