"""读外部爬虫库（v1 任务口径）：规则表转任务基线、单天按任务聚合、按入库时间找受影响的采集日。

库在 ShardingSphere 代理后面，整表聚合跑不出来，一律按天查。都是同步阻塞调用，由调用方放进线程池。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from typing import Any, cast

from platform_common.clock import BEIJING

from app.core.config import get_settings
from app.crawler.domain.identity import site_key
from app.crawler.repositories.source import mysql_connect, retry_mysql_read

logger = logging.getLogger("policy.cli.sync_crawler")

settings = get_settings()


def _text_value(value: Any, limit: int) -> str:
    """规则 JSON 里同一个键可能是字符串也可能是数字（如 author），统一成字符串。"""

    if value is None:
        return ""
    return str(value).strip()[:limit]


@retry_mysql_read
def fetch_rules() -> list[dict[str, Any]]:
    """读爬虫规则表。规则正文是 JSON 字符串，网站/标签都在 necessary_files 里。"""

    sql = f"SELECT id, correlation, state, rule FROM {settings.crawler_rules_table}"  # noqa: S608  表名经 Settings 校验为标识符，值走参数绑定
    with mysql_connect() as conn, conn.cursor() as cur:
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
            if not isinstance(need, dict):
                raise ValueError("necessary_files 必须是对象")
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
    if skipped:
        raise ValueError(f"规则表有 {skipped} 条无法解析，未更新任务基线，请修复后重试")
    for item in tasks:
        item["site_key"] = site_key(item["site_code"], item["site_name"], item["province_name"], item["city_name"])
    logger.info("rules_fetched total=%s usable=%s skipped=%s", len(rows), len(tasks), skipped)
    return tasks


@retry_mysql_read
def fetch_day(day: date) -> list[dict[str, Any]]:
    """单天按 (网站名称, 标签) 聚合；无名称时才使用编码。"""

    sql = f"""
        SELECT MAX(TRIM(COALESCE(author, ''))) AS site_code,
               TRIM(COALESCE(tag, '')) AS tag,
               MAX(site_name) AS site_name,
               MAX(prov_name) AS province_name,
               MAX(city_name) AS city_name,
               COUNT(*) AS row_count,
               SUM(name IS NOT NULL AND name <> '') AS named_count,
               SUM(content IS NOT NULL AND content <> '') AS content_count
        FROM {settings.crawler_data_table}
        WHERE collect_date = %s
        GROUP BY TRIM(COALESCE(site_name, '')), TRIM(COALESCE(tag, '')),
                 CASE WHEN TRIM(COALESCE(site_name, '')) = '' THEN TRIM(COALESCE(author, '')) ELSE '' END
    """  # noqa: S608  表名经 Settings 校验为标识符，值走参数绑定
    with mysql_connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (day.isoformat(),))
        rows = cast(list[dict[str, Any]], cur.fetchall())

    return [
        {
            "collect_date": day,
            "site_key": site_key(
                row["site_code"] or "", row["site_name"] or "", row["province_name"] or "", row["city_name"] or ""
            ),
            "identity_verified": True,
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


@retry_mysql_read
def fetch_affected_days(since_ts: datetime) -> tuple[set[date], datetime | None]:
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
    """  # noqa: S608  表名经 Settings 校验为标识符，值走参数绑定
    with mysql_connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (since_ts.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S"),))
        rows = cast(list[dict[str, Any]], cur.fetchall())

    days = {row["collect_date"] for row in rows if row["collect_date"]}
    stamps = [row["max_created"] for row in rows if row["max_created"]]
    return days, max(stamps).replace(tzinfo=BEIJING).astimezone(UTC) if stamps else None
