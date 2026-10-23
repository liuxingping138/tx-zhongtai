"""每日计划规则：以北京时间计算，错过多天只合并为一次增量。"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.aitag.domain.tasks import TASKS, job_code
from app.crawlconfig.domain.models import JOB_CODE

BEIJING = ZoneInfo("Asia/Shanghai")
CRAWLER_CONFIG = JOB_CODE
# 页面上的任务按这个顺序列出：爬虫同步、爬虫配置同步，然后是政策 AI 打标的三个任务。
JOBS = {
    "crawler": "爬虫监测增量同步",
    CRAWLER_CONFIG: "爬虫配置同步",
    **{job_code(task): name for task, name in TASKS.items()},
}
# 单次执行的超时：爬虫增量几分钟；配置同步只读规则表一列，几秒；AI 打标一批要等模型逐条回答，上千条要一两个小时。
TIMEOUTS = {"crawler": 1800, CRAWLER_CONFIG: 600, **{job_code(task): 6 * 3600 for task in TASKS}}
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
