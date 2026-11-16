"""AI 打标源库读取兼容导出，底层实现已收口至 ``app.common.policy_source``。"""

from __future__ import annotations

from app.common.mysql_source import mysql_connect
from app.common.policy_source import (
    PAGE_CONNECT_TIMEOUT,
    PAGE_READ_TIMEOUT,
    read_batch,
    read_by_ids,
    read_contents,
    read_contents_for_page,
    read_day_for_page,
    read_page,
)

__all__ = [
    "PAGE_CONNECT_TIMEOUT",
    "PAGE_READ_TIMEOUT",
    "mysql_connect",
    "read_batch",
    "read_by_ids",
    "read_contents",
    "read_contents_for_page",
    "read_day_for_page",
    "read_page",
]
