"""每日计划规则：以北京时间计算，错过多天只合并为一次增量。"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")
JOBS = {"crawler-v2": "爬虫监测增量同步"}
ACTIVE = ("queued", "running", "retrying")
MAX_ATTEMPTS = 3
LEADER_LOCK = 72120260929


def next_daily(now: datetime, daily_time: str) -> datetime:
    hour, minute = map(int, daily_time.split(":"))
    local = now.astimezone(BEIJING)
    due = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if due <= local:
        due += timedelta(days=1)
    return due.astimezone(UTC)


def retry_delay(attempt: int) -> timedelta:
    return timedelta(seconds=60 if attempt <= 1 else 300)
