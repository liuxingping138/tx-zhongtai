"""政策 AI 打标的设置和执行记录（任务调度页用）。"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, VersionConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.aitag.application.tagging import day_start, run_summary, today
from app.aitag.domain.models import PolicyAiConfig
from app.aitag.repositories import tagging as repo
from app.common import internal_clients
from app.common.audit_emit import enqueue_event

BATCH_SIZE_RANGE = (1, 20_000)
# 0 = 全文照传；要截就至少留 500 字。
CONTENT_RANGE = (500, 200_000)
PROMPT_FIELDS = ("type_prompt_id", "interpret_prompt_id", "opportunity_prompt_id")


def _config_out(config: PolicyAiConfig) -> dict[str, Any]:
    return {
        **{field: getattr(config, field) for field in PROMPT_FIELDS},
        "batch_size": config.batch_size,
        "content_max_chars": config.content_max_chars,
        "daily_cost_limit": str(config.daily_cost_limit),
        "cursor_date": config.cursor_date.isoformat(),
        "cursor_content_id": config.cursor_content_id,
        "version": config.version,
        "updated_at": format_beijing(config.updated_at),
        "updated_by_name": config.updated_by_name,
    }


async def overview(session: AsyncSession) -> dict[str, Any]:
    """设置、可选的上线模板（政策类）和今天、本月已花的钱。ai-service 不可用时模板列表为空，设置照样能看。"""

    config = await repo.config(session)
    try:
        templates = await internal_clients.ai("GET", "/internal/v1/online-templates", params={"category": "policy"})
        templates_error = ""
    except Exception as exc:  # noqa: BLE001  模板列表取不到不影响看设置和记录，原因显示在页面上
        templates, templates_error = [], f"取上线模板失败：{exc}"
    first_of_month = today().replace(day=1)
    return {
        "current": await _current(session),
        "config": _config_out(config),
        "templates": templates,
        "templates_error": templates_error,
        "spent_today": str(await repo.spent_since(session, day_start(today()))),
        "spent_month": str(await repo.spent_since(session, day_start(first_of_month))),
    }


def _in_range(value: int, bounds: tuple[int, int], label: str) -> int:
    if not bounds[0] <= value <= bounds[1]:
        raise ApiError(f"{label}要在 {bounds[0]}～{bounds[1]} 之间", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return value


async def update(session: AsyncSession, actor: Actor, values: dict[str, Any]) -> dict[str, Any]:
    config = await repo.config(session, lock=True)
    if int(values.get("version") or 0) != config.version:
        raise VersionConflictError("设置已被其他人修改，请刷新后重新保存")
    limit = Decimal(str(values["daily_cost_limit"]))
    if limit < 0:
        raise ApiError("每日费用上限不能是负数", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    cursor_date = date.fromisoformat(str(values["cursor_date"]))
    if cursor_date > today():
        raise ApiError("起始采集日期不能晚于今天", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    before = _config_out(config)
    for field in PROMPT_FIELDS:
        setattr(config, field, str(values.get(field) or "").strip())
    config.batch_size = _in_range(int(values["batch_size"]), BATCH_SIZE_RANGE, "每批条数")
    content_max = int(values["content_max_chars"])
    config.content_max_chars = 0 if content_max == 0 else _in_range(content_max, CONTENT_RANGE, "正文截取字数")
    config.daily_cost_limit = limit
    # 改了起始日期就从那天的第一条重新读；没改就保持当前进度。
    if cursor_date != config.cursor_date:
        config.cursor_date, config.cursor_content_id = cursor_date, ""
    config.version += 1
    config.updated_at, config.updated_by_name = utcnow(), actor.name
    after = _config_out(config)
    changed = {key: {"from": before[key], "to": after[key]} for key in after if before[key] != after[key]}
    await enqueue_event(
        session, event_type="policy.ai_tagging.config_updated", actor=actor, target_id="policy_ai", changes=changed
    )
    return after


async def runs(session: AsyncSession, page: int, page_size: int) -> dict[str, Any]:
    rows, total = await repo.page_runs(session, page, page_size)
    items = [
        {
            "id": str(row.id),
            **run_summary(row),
            "started_at": format_beijing(row.started_at),
            "finished_at": format_beijing(row.finished_at),
        }
        for row in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# 进行到哪一步 -> 这一步在 ai-service 的任务ID列。
_STAGE_RUN = {"typing": "type_run_id", "interpreting": "interpret_run_id", "opportunity": "opportunity_run_id"}
STAGE_NAMES = {"reading": "读取源政策", "typing": "类型判断", "interpreting": "政策解读", "opportunity": "市场机会"}


async def _current(session: AsyncSession) -> dict[str, Any] | None:
    """正在跑的那一批：在哪一步、这一步 ai-service 答到第几条。取不到进度不影响页面。"""

    run = await repo.running_run(session)
    if run is None:
        return None
    current: dict[str, Any] = {
        "id": str(run.id),
        "stage": run.stage,
        "stage_name": STAGE_NAMES.get(run.stage, run.stage),
        "started_at": format_beijing(run.started_at),
        "cost": str(run.cost),
        "done": None,
        "total": None,
    }
    ai_run_id = getattr(run, _STAGE_RUN.get(run.stage, ""), "") or ""
    if ai_run_id:
        try:
            status = await internal_clients.ai("GET", f"/internal/v1/pipeline-runs/{ai_run_id}")
            current.update(done=status.get("done_count"), total=status.get("total_count"))
        except Exception:  # noqa: BLE001, S110  进度是锦上添花，ai-service 暂时不可用时页面照常显示其余信息
            pass
    return current


BILLING_DAYS_MAX = 366


async def billing(session: AsyncSession, days: int) -> dict[str, Any]:
    """最近 days 天（含今天）每天的批次、费用和写入量，以及合计。没跑的日子不出现。"""

    days = max(1, min(days, BILLING_DAYS_MAX))
    rows = await repo.daily_billing(session, day_start(today() - timedelta(days=days - 1)))
    money = ("cost", "type_cost", "interpret_cost", "opportunity_cost")
    counts = ("runs", "source_rows", "tagged_rows", "interpret_rows")
    items = [
        {
            "day": str(row["day"]),
            **{key: str(row[key] or 0) for key in money},
            **{key: int(row[key] or 0) for key in counts},  # type: ignore[call-overload]  # SUM 出来是数值或空
        }
        for row in rows
    ]
    total = {key: str(sum((Decimal(item[key]) for item in items), Decimal(0))) for key in money}
    return {"days": days, "items": items, "total": total}
