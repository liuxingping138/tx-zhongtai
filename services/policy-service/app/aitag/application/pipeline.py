"""打标三步共用的部分：发起 ai-service 流水线任务、等它结束、取结果，并按当日额度控制费用。"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as day_time
from decimal import Decimal
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import BEIJING, utcnow
from platform_common.errors import ApiError, DependencyUnavailableError

from app.aitag.repositories import tagging as repo
from app.common import internal_clients
from app.common.errors import UserFacingError
from app.core.database import SessionLocal

POLL_SECONDS = 10
# 等 ai-service 跑完要一两个小时：中途它重建、某一次请求超时都很平常，连续这么多次问不到才算失败（约 5 分钟）。
POLL_MISSES = 30
# 沿用上一批答好的行之前，等那批 AI 任务停稳的最长时间。
SETTLE_SECONDS = 300
# 只沿用最近几天内失败的那批：再早的数据多半已经被后来的批次重新跑过了。
REUSE_DAYS = 3
FINISHED = {"done", "cancelled", "failed", "interrupted"}
# ai-service 对没轮到的行写「未执行（任务停止或中断）」：费用到上限或任务被停。这些行下批重做。
NOT_RUN = "未执行"
# 一批发给 ai-service 的行最多这么多字节（ai-service 的 PIPELINE_MAX_BYTES 是 64MB，留出余量）。
# 默认一批 1000 条、正文全文，长正文多的日子会超；超出的行记成未执行，读取进度、待办都不前移，下一批接着做。
PIPELINE_ROWS_BUDGET = 56 * 1024 * 1024
TOO_LARGE = f"{NOT_RUN}（这一批数据超过 AI 服务一次能收的大小，留到下一批）"
ROBOT = Actor(id="policy-ai-tagging", name="政策AI打标")
# 每一步在批次记录上的任务ID列 -> 这一步的费用列，账单按步骤拆。
STAGE_COST = {
    "type_run_id": "type_cost",
    "interpret_run_id": "interpret_cost",
    "opportunity_run_id": "opportunity_cost",
    "scenario_run_id": "scenario_cost",
    "enrich_run_id": "enrich_cost",
}


def today() -> date:
    return datetime.now(BEIJING).date()


def day_start(day: date) -> datetime:
    return datetime.combine(day, day_time.min, tzinfo=BEIJING).astimezone(UTC)


@dataclass
class Spend:
    """当日额度：上限 - 本批开始前今天已花 - 本批已花。每一步发起前按剩余额度设费用上限。"""

    limit: Decimal
    before: Decimal
    run: Decimal = Decimal(0)

    def remaining(self) -> Decimal:
        return self.limit - self.before - self.run


async def update_run(run_id: uuid.UUID, **values: Any) -> None:
    async with SessionLocal() as session:
        run = await repo.get_run(session, run_id)
        if run is not None:
            for key, value in values.items():
                setattr(run, key, value)
            await session.commit()


def cost_of(status: dict[str, Any]) -> Decimal:
    return Decimal(str(status.get("inference_cost") or 0)) + Decimal(str(status.get("search_cost") or 0))


async def stop_quietly(ai_run_id: str) -> None:
    """调度超时或进程停止时停掉 ai-service 那边的任务，别让它在后台继续花钱。停不掉也不影响收尾。"""

    with contextlib.suppress(Exception):
        await internal_clients.ai("POST", f"/internal/v1/pipeline-runs/{ai_run_id}/stop")


async def _wait(run_id: uuid.UUID, ai_run_id: str, spend: Spend) -> dict[str, Any]:
    misses = 0
    while True:
        try:
            status: dict[str, Any] = await internal_clients.ai("GET", f"/internal/v1/pipeline-runs/{ai_run_id}")
        except DependencyUnavailableError:
            # 一次没问到就让整批失败，下批会把同一批政策再问一遍、再花一遍钱。
            misses += 1
            if misses >= POLL_MISSES:
                raise
            await asyncio.sleep(POLL_SECONDS)
            continue
        misses = 0
        await update_run(run_id, cost=spend.run + cost_of(status))
        if status["status"] in FINISHED:
            return status
        await asyncio.sleep(POLL_SECONDS)


async def _settled(ai_run_id: str) -> dict[str, Any] | None:
    """那批 AI 任务停稳了没有：还在跑就叫停、等它收尾（在途的几行答完才写进文件）。停稳了返回它最后的状态，
    问不到、等不到就返回 None，不沿用。"""

    deadline = time.monotonic() + SETTLE_SECONDS
    stopped = False
    while True:
        try:
            status: dict[str, Any] = await internal_clients.ai("GET", f"/internal/v1/pipeline-runs/{ai_run_id}")
        except (ApiError, DependencyUnavailableError):
            return None
        if status["status"] in FINISHED:
            return status
        if not stopped:
            await stop_quietly(ai_run_id)
            stopped = True
        if time.monotonic() > deadline:
            return None
        await asyncio.sleep(POLL_SECONDS)


async def _book_final_cost(run_field: str, ai_run_id: str, final: Decimal) -> None:
    """上一批失败收尾时只补记到最后一次轮询到的花费：之后问不到 ai-service 的那段、叫停前在途几行的钱没记上，
    今日已花偏少、当天上限会被超过。那边停稳后按最终花费把差额补进那一批的步骤费用列。"""

    column = STAGE_COST[run_field]
    async with SessionLocal() as session:
        run = await repo.run_of_ai_task(session, run_field, ai_run_id)
        booked = Decimal(0) if run is None else getattr(run, column) or Decimal(0)
        if run is None or final <= booked:
            return
        setattr(run, column, final)
        run.cost = (run.cost or Decimal(0)) + (final - booked)
        await session.commit()


async def _reusable(run_id: uuid.UUID, run_field: str) -> str:
    """上一批失败了（中断、超时、轮询连不上、写库出错），它在 ai-service 那边已经答好的行这一批直接沿用，
    不再花钱重问：这一批读到的还是那些数据（读取进度没前移、待办还在）。"""

    async with SessionLocal() as session:
        since = utcnow() - timedelta(days=REUSE_DAYS)
        previous = await repo.failed_ai_run(session, run_field, current=run_id, since=since)
    status = await _settled(previous) if previous else None
    if status is None:
        return ""
    await _book_final_cost(run_field, previous, cost_of(status))
    return previous


async def ask(
    run_id: uuid.UUID, spend: Spend, *, prompt_id: str, rows: list[dict[str, str]], caller: str, run_field: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """用上线模板跑一批行，返回（任务状态，逐行结果）。结果和 rows 同序，没轮到的行 error 以「未执行」开头。

    ai-service 那边一行最多跑三轮：网络失败、格式不对的隔一会儿重问，这里拿到的已经是三轮之后的结果。
    """

    previous = await _reusable(run_id, run_field)
    sent = fitting_rows(rows)
    body = {"prompt_id": prompt_id, "rows": rows[:sent], "cost_limit": str(spend.remaining()), "caller_name": caller}
    created = await internal_clients.ai("POST", "/internal/v1/pipeline-runs", json={**body, "reuse_run_id": previous})
    ai_run_id = str(created["id"])
    await update_run(run_id, **{run_field: ai_run_id})
    try:
        status = await _wait(run_id, ai_run_id, spend)
    except BaseException:
        # 调度超时、进程停止、一直问不到：都先叫停那边，别让它在后台继续花钱。它已答好的行下一批沿用。
        await asyncio.shield(stop_quietly(ai_run_id))
        raise
    stage_cost = cost_of(status)
    spend.run += stage_cost
    await update_run(run_id, **{STAGE_COST[run_field]: stage_cost})
    if status["status"] == "failed" and not status.get("done_count"):
        # 一行都没跑就失败（模型不认识、快照丢了这类）：照常往下走会把整批记成「未执行」、批次却记成功，天天如此。
        raise UserFacingError(f"AI 服务没能执行这一批：{status.get('error_message') or '没有说明原因'}")
    data = await internal_clients.ai("GET", f"/internal/v1/pipeline-runs/{ai_run_id}/results")
    status["reused"] = int(created.get("reused") or 0)
    return status, [*data["items"], *({"error": TOO_LARGE, "items": []} for _ in rows[sent:])]


def fitting_rows(rows: list[dict[str, str]]) -> int:
    """从头数能装进 PIPELINE_ROWS_BUDGET 的行数，至少一行（一条政策正文最多 20 万字，不会单独超）。"""

    used = 0
    for index, row in enumerate(rows):
        used += len(json.dumps(row, ensure_ascii=False).encode()) + 1
        if used > PIPELINE_ROWS_BUDGET:
            return max(index, 1)
    return len(rows)


def reused_note(status: dict[str, Any]) -> str:
    count = int(status.get("reused") or 0)
    return f"（其中 {count} 条沿用上一批已答好的结果，没再花钱）" if count else ""


def not_run(result: dict[str, Any]) -> bool:
    return str(result.get("error") or "").startswith(NOT_RUN)
