"""读爬虫同事维护的规则表（crawler2021 库，一行一个栏目）。只读，只取网站编码和创建时间。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, cast

from app.common.mysql_source import mysql_connect, retry_mysql_read
from app.core.config import get_settings
from app.crawlconfig.domain.expand import ColumnRule


@dataclass
class RuleCodes:
    rows: int = 0
    # 网站编码 -> 这个网站最早那条规则的创建日期，也就是爬虫同事配好它的那天。
    # 只算按网站一行的旧规则（展开那天之前建的）。
    first_dates: dict[str, date] = field(default_factory=dict)
    # 老数据很多没填 site_code，关联不到信源，单独数出来提醒补。
    blank_rows: int = 0
    # 展开那天起建的规则：一条规则在信源表里展开成一行（见 domain.expand）。没开展开时为空。
    columns: list[ColumnRule] = field(default_factory=list)

    @property
    def codes(self) -> set[str]:
        return set(self.first_dates) | {rule.site_code for rule in self.columns}


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
def read_rule_codes(expand_from: date | None = None) -> RuleCodes:
    """规则表两三万行，整表读回来在本地取每个编码的最早创建日期，不在代理后做 GROUP BY。

    expand_from 那天起建的规则不并进网站的最早日期，单独列出来按栏目展开。
    """

    settings = get_settings()
    columns = "id, site_code, site_module_name, site_link, create_time"
    with mysql_connect(settings.crawler_mysql_db) as connection, connection.cursor() as cursor:
        sql = f"SELECT {columns} FROM {settings.crawler_rules_table}"  # noqa: S608  表名经 Settings 校验为标识符
        cursor.execute(sql)
        rows = cast(list[dict[str, Any]], cursor.fetchall())
    result = RuleCodes(rows=len(rows))
    for row in rows:
        code = str(row["site_code"] or "").strip()
        day = _day(row["create_time"])
        if not code or day is None:
            result.blank_rows += 1
            continue
        if expand_from is not None and day >= expand_from:
            result.columns.append(_column(row, code, day))
            continue
        known = result.first_dates.get(code)
        if known is None or day < known:
            result.first_dates[code] = day
    return result


def _column(row: dict[str, Any], code: str, day: date) -> ColumnRule:
    module = str(row.get("site_module_name") or "").strip()
    link = str(row.get("site_link") or "").strip()
    return ColumnRule(rule_id=str(row["id"]).strip(), site_code=code, module=module, link=link, day=day)
