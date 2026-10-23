"""读爬虫同事维护的规则表（crawler2021 库，一行一个栏目）。只读，只取网站编码和创建时间。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, cast

from app.common.mysql_source import mysql_connect, retry_mysql_read
from app.core.config import get_settings


@dataclass
class RuleCodes:
    rows: int = 0
    # 网站编码 -> 这个网站最早那条规则的创建日期，也就是爬虫同事配好它的那天。
    first_dates: dict[str, date] = field(default_factory=dict)
    # 老数据很多没填 site_code，关联不到信源，单独数出来提醒补。
    blank_rows: int = 0

    @property
    def codes(self) -> set[str]:
        return set(self.first_dates)


def _day(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


@retry_mysql_read
def read_rule_codes() -> RuleCodes:
    """规则表两三万行，只读两列整表读回来在本地取每个编码的最早创建日期，不在代理后做 GROUP BY。"""

    settings = get_settings()
    with mysql_connect(settings.crawler_mysql_db) as connection, connection.cursor() as cursor:
        sql = f"SELECT site_code, create_time FROM {settings.crawler_rules_table}"  # noqa: S608  表名经 Settings 校验为标识符
        cursor.execute(sql)
        rows = cast(list[dict[str, Any]], cursor.fetchall())
    result = RuleCodes(rows=len(rows))
    for row in rows:
        code = str(row["site_code"] or "").strip()
        day = _day(row["create_time"])
        if not code or day is None:
            result.blank_rows += 1
            continue
        known = result.first_dates.get(code)
        if known is None or day < known:
            result.first_dates[code] = day
    return result
