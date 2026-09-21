"""统一时钟与北京时间格式化。业务时间一律存 UTC，展示时转北京时间。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

BEIJING = timezone(timedelta(hours=8))


def utcnow() -> datetime:
    return datetime.now(UTC)


def format_beijing(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=UTC)
        return dt.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S")
    text = str(value)
    if "T" not in text and "Z" not in text and "+00:00" not in text:
        return text
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S")
