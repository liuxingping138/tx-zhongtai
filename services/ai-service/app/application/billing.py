"""费用账单和试发、多轮对话的记账。

所有模型调用都经过本服务：批量提问（含政策服务的定时打标）的费用记在批量任务上，试发和多轮对话每次调用记一行。
账单把两边按北京日期 × 模型 × 用途合起来，页面再按模型、按用途、按日期汇总和画图。
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import BEIJING, utcnow
from platform_common.errors import ApiError, ErrorCode
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.domain.llm_models import LlmModel, calc_costs
from app.domain.models import CallUsage
from app.repositories import billing as repo

logger = logging.getLogger("ai.billing")
MAX_DAYS = 366


class CallTally:
    """一次流式回答里的用量：最后的 usage 事件给 token；联网次数优先用 usage 里的，没有就数联网事件。"""

    def __init__(self) -> None:
        self.usage: dict[str, int] = {}
        self.search_events = 0

    def add(self, event: dict[str, Any]) -> None:
        if isinstance(event.get("usage"), dict):
            self.usage = event["usage"]
        elif event.get("tool_event", {}).get("stage") == "web_search_in_progress":
            self.search_events += 1

    @property
    def empty(self) -> bool:
        return not self.usage and not self.search_events


async def record_call(kind: str, model: LlmModel, tally: CallTally, actor: Actor) -> None:
    """记一次试发或多轮对话的花费。记账失败只写日志，不能让已经答完的回答报错。"""

    if tally.empty:
        return
    when = utcnow()
    input_tokens = int(tally.usage.get("input_tokens", 0))
    output_tokens = int(tally.usage.get("output_tokens", 0))
    searches = int(tally.usage.get("web_search", tally.search_events))
    inference, search = calc_costs(model, input_tokens, output_tokens, searches, when)
    try:
        async with SessionLocal() as session:
            repo.add_call(
                session,
                CallUsage(
                    kind=kind,
                    model_id=model.id,
                    model_name=model.name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    search_calls=searches,
                    inference_cost=inference,
                    search_cost=search,
                    created_at=when,
                    created_by_id=actor.id,
                    created_by_name=actor.name,
                ),
            )
            await session.commit()
    except Exception:  # 记账失败不影响用户已经拿到的回答
        logger.exception("call_usage_record_failed kind=%s model=%s", kind, model.id)


def _bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    if date_from > date_to:
        raise ApiError("开始日期不能晚于结束日期", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if (date_to - date_from).days + 1 > MAX_DAYS:
        raise ApiError(f"一次最多查 {MAX_DAYS} 天", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    start = datetime.combine(date_from, time.min, tzinfo=BEIJING).astimezone(UTC)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=BEIJING).astimezone(UTC)
    return start, end


async def daily(session: AsyncSession, date_from: date, date_to: date) -> dict[str, Any]:
    """北京日期 [date_from, date_to] 里每天、每个模型、每种用途的次数、token 和费用。没花钱的组合不出现。"""

    since, until = _bounds(date_from, date_to)
    rows = await repo.daily(session, since, until)
    items = [
        {
            "day": str(row["day"]),
            "model": row["model"],
            "purpose": row["purpose"],
            "calls": int(row["calls"] or 0),
            "input_tokens": int(row["input_tokens"] or 0),
            "output_tokens": int(row["output_tokens"] or 0),
            "cost": str(Decimal(row["cost"] or 0)),
        }
        for row in rows
    ]
    items.sort(key=lambda item: (item["day"], item["model"], item["purpose"]))
    return {"date_from": date_from.isoformat(), "date_to": date_to.isoformat(), "items": items}
