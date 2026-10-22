"""打标三步共用的部分：发起 ai-service 流水线任务、等它结束、取结果，并按当日额度控制费用。"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import BEIJING

from app.aitag.repositories import tagging as repo
from app.common import internal_clients
from app.core.database import SessionLocal

POLL_SECONDS = 10
FINISHED = {"done", "cancelled", "failed", "interrupted"}
# ai-service 对没轮到的行写「未执行（任务停止或中断）」：费用到上限或任务被停。这些行下批重做。
NOT_RUN = "未执行"
ROBOT = Actor(id="policy-ai-tagging", name="政策AI打标")


def today() -> date:
    return datetime.now(BEIJING).date()


def day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=BEIJING).astimezone(UTC)


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
    while True:
        status: dict[str, Any] = await internal_clients.ai("GET", f"/internal/v1/pipeline-runs/{ai_run_id}")
        await update_run(run_id, cost=spend.run + cost_of(status))
        if status["status"] in FINISHED:
            return status
        await asyncio.sleep(POLL_SECONDS)


async def ask(
    run_id: uuid.UUID, spend: Spend, *, prompt_id: str, rows: list[dict[str, str]], caller: str, run_field: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """用上线模板跑一批行，返回（任务状态，逐行结果）。结果和 rows 同序，没轮到的行 error 以「未执行」开头。"""

    created = await internal_clients.ai(
        "POST",
        "/internal/v1/pipeline-runs",
        json={"prompt_id": prompt_id, "rows": rows, "cost_limit": str(spend.remaining()), "caller_name": caller},
    )
    ai_run_id = str(created["id"])
    await update_run(run_id, **{run_field: ai_run_id})
    try:
        status = await _wait(run_id, ai_run_id, spend)
    except asyncio.CancelledError:
        await asyncio.shield(stop_quietly(ai_run_id))
        raise
    spend.run += cost_of(status)
    data = await internal_clients.ai("GET", f"/internal/v1/pipeline-runs/{ai_run_id}/results")
    return status, list(data["items"])


def not_run(result: dict[str, Any]) -> bool:
    return str(result.get("error") or "").startswith(NOT_RUN)
