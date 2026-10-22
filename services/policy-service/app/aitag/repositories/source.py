"""读源政策：bid_analyse 的 csys_policy_info（政策）+ csys_policy_info_content（正文，按 content_id 一对一）。只读。

代理后整表扫描跑不动，按采集日逐天读（collect_date 有索引），日内按 content_id 排序分页：
读取进度就是（采集日，该日最后一个 content_id），换天时 content_id 从空串开始。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, cast

from app.common.mysql_source import mysql_connect, retry_mysql_read
from app.core.config import get_settings

# status：0 正常、-1 删除，默认正常（可能为空）。删掉的不打标。
_BATCH_SQL = """
    SELECT content_id, name, introduced_department, department_industry, level, prov_id, prov_name,
           city_id, city_name, introduced_date, original_link, collect_date
    FROM csys_policy_info
    WHERE collect_date = %s AND content_id > %s AND (status IS NULL OR status <> '-1')
    ORDER BY content_id LIMIT %s
"""
_CONTENT_CHUNK = 200


@retry_mysql_read
def read_batch(cursor_date: date, cursor_id: str, limit: int, until: date) -> list[dict[str, Any]]:
    """从进度之后读最多 limit 条，跨天往后读到 until（含）为止。"""

    rows: list[dict[str, Any]] = []
    day, last = cursor_date, cursor_id
    with mysql_connect(get_settings().policy_source_db) as connection, connection.cursor() as cursor:
        while day <= until and len(rows) < limit:
            wanted = limit - len(rows)
            cursor.execute(_BATCH_SQL, (day, last, wanted))
            got = cast(list[dict[str, Any]], cursor.fetchall())
            rows.extend(got)
            if len(got) < wanted:
                day, last = day + timedelta(days=1), ""
            else:
                last = str(got[-1]["content_id"])
    return rows


@retry_mysql_read
def read_contents(content_ids: list[str]) -> dict[str, str]:
    contents: dict[str, str] = {}
    with mysql_connect(get_settings().policy_source_db) as connection, connection.cursor() as cursor:
        for start in range(0, len(content_ids), _CONTENT_CHUNK):
            chunk = content_ids[start : start + _CONTENT_CHUNK]
            marks = ", ".join(["%s"] * len(chunk))
            cursor.execute(
                f"SELECT content_id, content FROM csys_policy_info_content WHERE content_id IN ({marks})",  # noqa: S608  只拼占位符，值走参数
                chunk,
            )
            found = cast(list[dict[str, Any]], cursor.fetchall())
            contents.update({str(row["content_id"]): str(row["content"] or "") for row in found})
    return contents
