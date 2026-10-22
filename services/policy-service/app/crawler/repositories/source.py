"""爬虫监测读的采集总表在 crawler2021 库。连接和瞬时错误重试在 app.common.mysql_source。"""

from __future__ import annotations

import pymysql

from app.common.mysql_source import mysql_connect as connect_database
from app.common.mysql_source import retry_mysql_read
from app.core.config import get_settings

__all__ = ["mysql_connect", "retry_mysql_read"]


def mysql_connect() -> pymysql.connections.Connection:
    return connect_database(get_settings().crawler_mysql_db)
