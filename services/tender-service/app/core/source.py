"""唯一的源库执行入口：仅接受 SELECT，不提供提交、批量执行或 DDL 能力。"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pymysql
from platform_common.errors import DependencyUnavailableError
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings

# 外部表包含多种字符串、日期、Decimal 类型，数据库驱动返回的行在响应层统一序列化。
Row = dict[str, Any]
_FORBIDDEN_SQL = re.compile(
    r"\b(?:FOR\s+UPDATE|LOCK\s+IN\s+SHARE\s+MODE|INTO\s+(?:OUTFILE|DUMPFILE))\b",
    re.IGNORECASE,
)


class Reader:
    def __init__(self, connection: pymysql.connections.Connection[pymysql.cursors.DictCursor]) -> None:
        self._connection = connection

    def select(self, sql: str, params: tuple[object, ...] = ()) -> list[Row]:
        if not sql.lstrip().upper().startswith("SELECT ") or ";" in sql or _FORBIDDEN_SQL.search(sql):
            raise ValueError("招中标数据源仅允许单条只读 SELECT 查询")
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())


@contextmanager
def source_reader(*, counting: bool = False) -> Iterator[Reader]:
    settings = get_settings()
    if not settings.mysql_host:
        raise DependencyUnavailableError("招中标数据源尚未配置")
    try:
        connection = pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database="bid_analyse",
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=settings.mysql_connect_timeout,
            read_timeout=settings.mysql_count_timeout if counting else settings.mysql_read_timeout,
            write_timeout=settings.mysql_read_timeout,
        )
        try:
            with contextlib.suppress(pymysql.MySQLError), connection.cursor() as cur:
                cur.execute("SET SESSION TRANSACTION READ ONLY")
            yield Reader(connection)
        finally:
            connection.close()
    except pymysql.MySQLError as exc:
        raise DependencyUnavailableError("招中标源库查询失败或超时，请缩小筛选范围后重试") from exc


def _ready() -> bool:
    with source_reader() as reader:
        return bool(reader.select("SELECT 1 AS ready"))


async def check_source_ready() -> bool:
    return await run_in_threadpool(_ready)
