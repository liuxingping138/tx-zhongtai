from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))


def utcnow() -> datetime:
    return datetime.now(UTC)


def assume_beijing(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=BEIJING)
    return value
