"""唯一的源库执行入口：仅接受 SELECT，不提供提交、批量执行或 DDL 能力。"""

from __future__ import annotations

import contextlib
import queue
import re
import threading
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
_POOL_MAX_PER_KEY = 8
_MAX_ACTIVE_PER_KEY = 16
_PoolKey = tuple[str, int, str, int]
_POOL: dict[_PoolKey, queue.LifoQueue[pymysql.connections.Connection[pymysql.cursors.DictCursor]]] = {}
_SEMAPHORES: dict[_PoolKey, threading.Semaphore] = {}
_POOL_LOCK = threading.Lock()


def _bucket(key: _PoolKey) -> queue.LifoQueue[pymysql.connections.Connection[pymysql.cursors.DictCursor]]:
    with _POOL_LOCK:
        q = _POOL.get(key)
        if q is None:
            q = queue.LifoQueue(maxsize=_POOL_MAX_PER_KEY)
            _POOL[key] = q
        return q


def _semaphore(key: _PoolKey) -> threading.Semaphore:
    with _POOL_LOCK:
        sem = _SEMAPHORES.get(key)
        if sem is None:
            sem = threading.Semaphore(_MAX_ACTIVE_PER_KEY)
            _SEMAPHORES[key] = sem
        return sem


def clear_pool() -> None:
    with _POOL_LOCK:
        buckets = list(_POOL.values())
        _POOL.clear()
    for q in buckets:
        while not q.empty():
            with contextlib.suppress(Exception):
                q.get_nowait().close()


class Reader:
    def __init__(self, connection: pymysql.connections.Connection[pymysql.cursors.DictCursor]) -> None:
        self._connection = connection

    def select(self, sql: str, params: tuple[object, ...] = ()) -> list[Row]:
        if not sql.lstrip().upper().startswith("SELECT ") or ";" in sql or _FORBIDDEN_SQL.search(sql):
            raise ValueError("招中标数据源仅允许单条只读 SELECT 查询")
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())


def _acquire_connection(
    bucket: queue.LifoQueue[pymysql.connections.Connection[pymysql.cursors.DictCursor]],
    *,
    read_timeout: int,
) -> pymysql.connections.Connection[pymysql.cursors.DictCursor]:
    while not bucket.empty():
        candidate = bucket.get_nowait()
        try:
            # 不让驱动自己重连：重连出来的新会话没有 SET SESSION TRANSACTION READ ONLY。
            # 坏了就关掉，下面按新连接重新建、重新设只读。
            candidate.ping(reconnect=False)
            return candidate
        except pymysql.MySQLError:
            with contextlib.suppress(Exception):
                candidate.close()
    settings = get_settings()
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
        read_timeout=read_timeout,
        write_timeout=settings.mysql_read_timeout,
    )
    with contextlib.suppress(pymysql.MySQLError), connection.cursor() as cur:
        cur.execute("SET SESSION TRANSACTION READ ONLY")
    return connection


@contextmanager
def source_reader(*, counting: bool = False) -> Iterator[Reader]:
    settings = get_settings()
    if not settings.mysql_host:
        raise DependencyUnavailableError("招中标数据源尚未配置")
    read_timeout = settings.mysql_count_timeout if counting else settings.mysql_read_timeout
    key: _PoolKey = (settings.mysql_host, settings.mysql_port, settings.mysql_user, read_timeout)
    sem = _semaphore(key)
    if not sem.acquire(timeout=settings.mysql_connect_timeout):
        raise DependencyUnavailableError("招中标源库连接繁忙，请稍后重试")
    bucket = _bucket(key)
    connection: pymysql.connections.Connection[pymysql.cursors.DictCursor] | None = None
    broken = False
    try:
        connection = _acquire_connection(bucket, read_timeout=read_timeout)
        try:
            yield Reader(connection)
        except (pymysql.MySQLError, OSError):
            broken = True
            raise
    except pymysql.MySQLError as exc:
        broken = True
        raise DependencyUnavailableError("招中标源库查询失败或超时，请缩小筛选范围后重试") from exc
    finally:
        if connection is not None:
            if broken:
                with contextlib.suppress(Exception):
                    connection.close()
            else:
                try:
                    bucket.put_nowait(connection)
                except queue.Full:
                    with contextlib.suppress(Exception):
                        connection.close()
        sem.release()


def _ready() -> bool:
    with source_reader() as reader:
        return bool(reader.select("SELECT 1 AS ready"))


async def check_source_ready() -> bool:
    return await run_in_threadpool(_ready)
