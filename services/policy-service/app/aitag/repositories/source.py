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
# 重新判断类型：按源政策 ID 直接取，和按天读取用同一组字段。
_BY_IDS_SQL = _BATCH_SQL.split("WHERE", maxsplit=1)[0] + "WHERE content_id IN ({marks})"
_CONTENT_SQL = "SELECT content_id, content FROM csys_policy_info_content WHERE content_id IN ({marks})"
# 页面上点开一条政策看正文：人在页面上等（前端 30 秒超时），源库出故障要很快说清。
# 不能沿用同步任务的 30 秒连接、20 分钟读取和重试：每次请求占一个线程，
# 几十个卡住的请求会把同服务的 Excel 导入导出一起堵住。源库单条读取实测 0.2 秒。
PAGE_CONNECT_TIMEOUT = 5
PAGE_READ_TIMEOUT = 20


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
def read_by_ids(content_ids: list[str]) -> list[dict[str, Any]]:
    """按源政策 ID 取政策（不管采集日、不管是否删除），保持传入的顺序。源库里已经没有的不返回。"""

    found: dict[str, dict[str, Any]] = {}
    with mysql_connect(get_settings().policy_source_db) as connection, connection.cursor() as cursor:
        for start in range(0, len(content_ids), _CONTENT_CHUNK):
            chunk = content_ids[start : start + _CONTENT_CHUNK]
            cursor.execute(_BY_IDS_SQL.format(marks=", ".join(["%s"] * len(chunk))), chunk)
            for row in cast(list[dict[str, Any]], cursor.fetchall()):
                found[str(row["content_id"])] = row
    return [found[content_id] for content_id in content_ids if content_id in found]


def _contents(cursor: Any, content_ids: list[str]) -> dict[str, str]:
    contents: dict[str, str] = {}
    for start in range(0, len(content_ids), _CONTENT_CHUNK):
        chunk = content_ids[start : start + _CONTENT_CHUNK]
        marks = ", ".join(["%s"] * len(chunk))
        cursor.execute(_CONTENT_SQL.format(marks=marks), chunk)
        found = cast(list[dict[str, Any]], cursor.fetchall())
        contents.update({str(row["content_id"]): str(row["content"] or "") for row in found})
    return contents


@retry_mysql_read
def read_contents(content_ids: list[str]) -> dict[str, str]:
    with mysql_connect(get_settings().policy_source_db) as connection, connection.cursor() as cursor:
        return _contents(cursor, content_ids)


def _connect_for_page() -> Any:
    database = get_settings().policy_source_db
    return mysql_connect(database, connect_timeout=PAGE_CONNECT_TIMEOUT, read_timeout=PAGE_READ_TIMEOUT)


def read_day_for_page(day: date, limit: int) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """「从数据库取测试数据」：人在页面上等，一次连接读这天前 limit 条政策和它们的正文。超时同 read_page，不重试。"""

    with _connect_for_page() as connection, connection.cursor() as cursor:
        cursor.execute(_BATCH_SQL, (day, "", limit))
        rows = cast(list[dict[str, Any]], cursor.fetchall())
        return rows, _contents(cursor, [str(row["content_id"]) for row in rows])


def read_contents_for_page(content_ids: list[str]) -> dict[str, str]:
    with _connect_for_page() as connection, connection.cursor() as cursor:
        return _contents(cursor, content_ids)


def read_page(content_id: str) -> tuple[dict[str, Any] | None, str | None]:
    """页面看正文用：一条政策和它的正文（网页源码），源库里没有的是 None。

    一次连接读两张表；连接 5 秒、读 20 秒超时，不重试，连不上直接抛出，由调用方回 503。
    """

    database = get_settings().policy_source_db
    with (
        mysql_connect(database, connect_timeout=PAGE_CONNECT_TIMEOUT, read_timeout=PAGE_READ_TIMEOUT) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(_BY_IDS_SQL.format(marks="%s"), [content_id])
        row = cast(dict[str, Any] | None, cursor.fetchone())
        if row is None:
            return None, None
        cursor.execute(_CONTENT_SQL.format(marks="%s"), [content_id])
        content = cast(dict[str, Any] | None, cursor.fetchone())
    return row, None if content is None else str(content["content"] or "")
