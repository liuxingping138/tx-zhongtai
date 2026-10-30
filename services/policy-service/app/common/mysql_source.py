"""外部爬虫 MySQL（前面挂 ShardingSphere 代理）的只读连接，爬虫监测同步和政策 AI 打标共用。

同一个实例上有多个库：爬虫监测读 crawler2021 的采集总表，政策 AI 打标读 bid_analyse 的政策表和正文表。
默认的超时按 worker 里跑的同步定：连接 30 秒、读 20 分钟，瞬时错误重试。HTTP 进程里只有点开政策看正文会连，
它有自己的短超时、不重试（``app.aitag.repositories.source.read_page``）。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from functools import wraps

import pymysql

from app.core.config import get_settings

logger = logging.getLogger("policy.mysql_source")

# 只重试瞬时连接错误：连不上、连接中断、读超时。认证失败和 SQL 错误重试也没用。
_TRANSIENT_ERRORS = {2002, 2003, 2006, 2013, 2055}
_MAX_ATTEMPTS = 3


def retry_mysql_read[**P, R](operation: Callable[P, R]) -> Callable[P, R]:
    """只重试瞬时连接错误；每次重新连接，认证和 SQL 错误立即失败。"""

    @wraps(operation)
    def read(*args: P.args, **kwargs: P.kwargs) -> R:
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return operation(*args, **kwargs)
            except pymysql.err.OperationalError as exc:
                if not exc.args or exc.args[0] not in _TRANSIENT_ERRORS or attempt == _MAX_ATTEMPTS:
                    raise
                logger.warning("source_read_retry operation=%s attempt=%s", operation.__name__, attempt)
                time.sleep(2 ** (attempt - 1))
        raise AssertionError("unreachable")

    return read


# 批量导入日单天可达数十万行，实测单日聚合最长约 7 分钟，留足余量。
SYNC_CONNECT_TIMEOUT = 30
SYNC_READ_TIMEOUT = 1200


def mysql_connect(
    database: str, *, connect_timeout: int = SYNC_CONNECT_TIMEOUT, read_timeout: int = SYNC_READ_TIMEOUT
) -> pymysql.connections.Connection:
    settings = get_settings()
    if not settings.crawler_mysql_host:
        raise RuntimeError("未配置 POLICY_CRAWLER_MYSQL_HOST，无法读取爬虫库")
    return pymysql.connect(
        host=settings.crawler_mysql_host,
        port=settings.crawler_mysql_port,
        user=settings.crawler_mysql_user,
        password=settings.crawler_mysql_password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        write_timeout=read_timeout,
    )
