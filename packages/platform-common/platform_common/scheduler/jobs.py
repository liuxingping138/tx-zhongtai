"""定时任务的登记项与时间、重试规则。各服务把自己的任务写成 Job 交给 Scheduler，引擎不认识任何具体业务。"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

BEIJING = ZoneInfo("Asia/Shanghai")
ACTIVE = ("queued", "running", "retrying")
MAX_ATTEMPTS = 3
DEFAULT_TIMEOUT = 1800
# 执行通道：每条通道同一时刻只跑一条，不同通道并行。按小时算的任务（如 AI 打标一批最长 6 小时）走长通道，
# 免得几秒、几分钟就完的同步在后面排几个小时。
SHORT_LANE = "short"
LONG_LANE = "long"


class UserFacingError(RuntimeError):
    """能原样显示给页面、重试也没用的失败（没选模板、上游明确拒绝）：直接失败，让人去改设置。

    其他异常页面上只显示类型名，避免把连接串、SQL 参数透出去。
    """


@dataclass(frozen=True)
class Job:
    """一个定时任务。execute 拿到本次的批次编号自己开会话执行；其余钩子都可省。

    没有批次表的简单任务（如清理）可以让 execute 直接返回结果摘要，记进执行记录。

    - abandon：超时或进程中断时把还停在 running 的批次收成失败，和执行记录同一事务提交
    - summary：批次的结果摘要。给了它，执行记录只在摘要的 status 是 success 时才算成功；
      没给就以 execute 不抛异常为成功
    - watermark：页面「数据进度」显示的水位
    - public_errors：RuntimeError 的信息以这些前缀开头时原样显示（例如「已有同步正在运行」）
    - cost_resource：会花钱的任务（如调大模型）。改计划、手动执行除了 system.scheduler 的完整档，
      还要这个资源的完整档：能排班的人不一定能决定花钱
    - lane：执行通道，默认短通道。同一通道的任务一条一条跑，不同通道互不等待；同一任务仍然最多一条在排队或执行
    """

    code: str
    name: str
    execute: Callable[[uuid.UUID], Awaitable[dict[str, Any] | None]]
    timeout_seconds: float = DEFAULT_TIMEOUT
    abandon: Callable[[AsyncSession, uuid.UUID, str], Awaitable[None]] | None = None
    summary: Callable[[AsyncSession, uuid.UUID], Awaitable[dict[str, Any] | None]] | None = None
    watermark: Callable[[AsyncSession], Awaitable[datetime | None]] | None = None
    public_errors: tuple[str, ...] = ()
    cost_resource: str | None = None
    lane: str = SHORT_LANE


def next_daily(now: datetime, daily_time: str) -> datetime:
    """北京时间下一个 HH:MM。到点当刻算已过，排到明天。"""

    hour, minute = map(int, daily_time.split(":"))
    local = now.astimezone(BEIJING)
    due = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if due <= local:
        due += timedelta(days=1)
    return due.astimezone(UTC)


def retry_delay(attempt: int) -> timedelta:
    return timedelta(seconds=60 if attempt <= 1 else 300)


def claim_failure(error: str | None, sync_status: str | None) -> str | None:
    """有结果摘要的任务，成功只认批次已经写成 success。超时或中断不能记成成功。"""

    if error:
        return error
    if sync_status == "success":
        return None
    return "同步批次未成功完成"


def fail_run(row: Any, message: str, now: datetime, *, retry: bool = True) -> None:
    """失败后按次数退避重试；retry=False 或次数用完直接失败。"""

    row.error_message = message
    if retry and row.attempts < MAX_ATTEMPTS:
        row.status = "retrying"
        row.available_at = now + retry_delay(row.attempts)
    else:
        row.status = "failed"
        row.finished_at = now
