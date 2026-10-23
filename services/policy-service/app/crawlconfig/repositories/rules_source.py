"""读爬虫同事维护的规则表（crawler2021 库，一行一个栏目）。只读，只取网站编码。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from app.common.mysql_source import mysql_connect, retry_mysql_read
from app.core.config import get_settings


@dataclass
class RuleCodes:
    rows: int = 0
    codes: set[str] = field(default_factory=set)
    # 老数据很多没填 site_code，关联不到信源，单独数出来提醒补。
    blank_rows: int = 0


@retry_mysql_read
def read_rule_codes() -> RuleCodes:
    """规则表两三万行，只读一列，整表读回来在本地去重，不在代理后做 DISTINCT。"""

    settings = get_settings()
    with mysql_connect(settings.crawler_mysql_db) as connection, connection.cursor() as cursor:
        cursor.execute(f"SELECT site_code FROM {settings.crawler_rules_table}")  # noqa: S608  表名经 Settings 校验为标识符
        rows = cast(list[dict[str, Any]], cursor.fetchall())
    result = RuleCodes(rows=len(rows))
    for row in rows:
        code = str(row["site_code"] or "").strip()
        if code:
            result.codes.add(code)
        else:
            result.blank_rows += 1
    return result
