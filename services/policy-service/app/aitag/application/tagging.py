"""政策 AI 打标的一批：读源政策 → 用上线模板判断政策类型 → 写基础标签 → 进度前移。

由任务调度（app.worker.scheduler）调用，一次执行就是一批。
模型调用在 ai-service 的 worker 里跑，这里只发起、等待、取结果。
费用：发起前先看今天花了多少，剩余额度作为这一批的费用上限传给 ai-service，到上限它自己停。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

import anyio
from platform_common.actors import Actor
from platform_common.clock import BEIJING, utcnow

from app.aitag.domain import rules
from app.aitag.domain.models import PolicyAiConfig, PolicyAiRun
from app.aitag.repositories import source
from app.aitag.repositories import tagging as repo
from app.common import internal_clients
from app.common.audit_emit import enqueue_event
from app.common.errors import UserFacingError
from app.core.database import SessionLocal
from app.policy.domain.models import BASE_TAG_FIELDS, BaseTag, content_hash

logger = logging.getLogger("policy.aitag")
POLL_SECONDS = 10
FINISHED = {"done", "cancelled", "failed", "interrupted"}
NOT_RUN = "未执行"
ROBOT = Actor(id="policy-ai-tagging", name="政策AI打标")


def today() -> date:
    return datetime.now(BEIJING).date()


def day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=BEIJING).astimezone(UTC)


async def _update(run_id: uuid.UUID, **values: Any) -> None:
    async with SessionLocal() as session:
        run = await repo.get_run(session, run_id)
        if run is not None:
            for key, value in values.items():
                setattr(run, key, value)
            await session.commit()


async def policy_type_names() -> list[str]:
    data = await internal_clients.codebook("GET", "/internal/v1/code-tables/policy_types")
    lines = str(data["text"]).split("\n")[1:]
    return [line.split("\t")[0] for line in lines if line.strip()]


def _cost(status: dict[str, Any]) -> Decimal:
    return Decimal(str(status.get("inference_cost") or 0)) + Decimal(str(status.get("search_cost") or 0))


async def _wait(run_id: uuid.UUID, ai_run_id: str) -> dict[str, Any]:
    while True:
        status: dict[str, Any] = await internal_clients.ai("GET", f"/internal/v1/pipeline-runs/{ai_run_id}")
        await _update(run_id, cost=_cost(status))
        if status["status"] in FINISHED:
            return status
        await asyncio.sleep(POLL_SECONDS)


async def _stop_quietly(ai_run_id: str) -> None:
    """调度超时或进程停止时停掉 ai-service 那边的任务，别让它在后台继续花钱。停不掉也不影响收尾。"""

    with contextlib.suppress(Exception):
        await internal_clients.ai("POST", f"/internal/v1/pipeline-runs/{ai_run_id}/stop")


def _write_base_tag(session: Any, existing: BaseTag | None, source_row: dict[str, Any], values: dict[str, str]) -> bool:
    """有这条政策的 AI 行就更新；人工在打标之后改过的不覆盖。返回是否写入。"""

    now = utcnow()
    if existing is not None:
        if existing.tagged_at is not None and existing.updated_at > existing.tagged_at:
            return False
        for key, value in values.items():
            setattr(existing, key, value)
        existing.refresh_hash()
        existing.version += 1
        existing.tagged_at = existing.updated_at = now
        existing.updated_by_id, existing.updated_by_name = ROBOT.id, ROBOT.name
        return True
    session.add(
        BaseTag(
            content_hash=content_hash(values, BASE_TAG_FIELDS),
            source_content_id=str(source_row["content_id"]),
            tagged_at=now,
            version=1,
            created_at=now,
            created_by_id=ROBOT.id,
            created_by_name=ROBOT.name,
            updated_at=now,
            updated_by_id=ROBOT.id,
            updated_by_name=ROBOT.name,
            **values,
        )
    )
    return True


async def _save(
    run_id: uuid.UUID,
    rows: list[dict[str, Any]],
    results: list[dict[str, Any]],
    known: list[str],
) -> dict[str, int]:
    processed = rules.resume_point(results, NOT_RUN)
    done_rows, done_results = rows[:processed], results[:processed]
    tagged = failed = 0
    seen: set[str] = set()
    async with SessionLocal() as session:
        existing = await repo.base_tags_by_source(session, [str(row["content_id"]) for row in done_rows])
        for row, result in zip(done_rows, done_results, strict=True):
            types, remark = rules.tagging_outcome(result, known)
            failed += 1 if remark else 0
            values = rules.base_tag_values(row, types, remark)
            current = existing.get(str(row["content_id"]))
            digest = content_hash(values, BASE_TAG_FIELDS)
            # 手工导入过、或同一批里有一模一样的一行（各地转发同一文件），不重复建：内容哈希唯一。
            if current is None and (digest in seen or await repo.base_tag_by_hash(session, digest)):
                continue
            seen.add(digest)
            tagged += 1 if _write_base_tag(session, current, row, values) else 0
        locked = await repo.config(session, lock=True)
        if done_rows:
            last = done_rows[-1]
            locked.cursor_date, locked.cursor_content_id = last["collect_date"], str(last["content_id"])
        await enqueue_event(
            session,
            event_type="policy.ai_tagging.tagged",
            actor=ROBOT,
            target_id=str(run_id),
            extra={"rows": len(done_rows), "tagged": tagged, "failed": failed},
        )
        await session.commit()
    return {"processed": processed, "tagged": tagged, "failed": failed}


def _cursor_text(day: date, content_id: str) -> str:
    return f"{day.isoformat()} {content_id}".strip()


async def run_batch(run_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        config = await repo.config(session)
        spent = await repo.spent_since(session, day_start(today()))
        session.add(
            PolicyAiRun(
                id=run_id,
                status="running",
                stage="reading",
                source_from=_cursor_text(config.cursor_date, config.cursor_content_id),
                started_at=utcnow(),
            )
        )
        await session.commit()
    try:
        note = await _run(run_id, config, spent)
        await _update(run_id, status="success", stage="done", note=note, finished_at=utcnow())
    except Exception as exc:
        message = str(exc) if isinstance(exc, UserFacingError) else f"执行失败（{type(exc).__name__}）"
        await _update(run_id, status="failed", error_message=message[:2000], finished_at=utcnow())
        raise


async def _run(run_id: uuid.UUID, config: PolicyAiConfig, spent: Decimal) -> str:
    if not config.type_prompt_id:
        raise UserFacingError("还没有选「政策类型判断」用的上线模板，请先在任务调度页设置")
    remaining = config.daily_cost_limit - spent
    if remaining <= 0:
        return f"今日已花 {spent:.2f} 元，达到每日上限 {config.daily_cost_limit:.2f} 元，本次未打标"
    rows = await anyio.to_thread.run_sync(
        source.read_batch, config.cursor_date, config.cursor_content_id, config.batch_size, today()
    )
    if not rows:
        return "没有新的源政策"
    ids = [str(row["content_id"]) for row in rows]
    contents = await anyio.to_thread.run_sync(source.read_contents, ids)
    prompt_rows = [
        rules.prompt_row(row, contents.get(str(row["content_id"])), config.content_max_chars) for row in rows
    ]
    known = await policy_type_names()
    await _update(run_id, stage="typing", source_rows=len(rows))
    created = await internal_clients.ai(
        "POST",
        "/internal/v1/pipeline-runs",
        json={
            "prompt_id": config.type_prompt_id,
            "rows": prompt_rows,
            "cost_limit": str(remaining),
            "caller_name": "政策AI打标·类型判断",
        },
    )
    ai_run_id = str(created["id"])
    await _update(run_id, type_run_id=ai_run_id)
    try:
        status = await _wait(run_id, ai_run_id)
    except asyncio.CancelledError:
        await asyncio.shield(_stop_quietly(ai_run_id))
        raise
    data = await internal_clients.ai("GET", f"/internal/v1/pipeline-runs/{ai_run_id}/results")
    counts = await _save(run_id, rows, data["items"], known)
    last = rows[counts["processed"] - 1] if counts["processed"] else None
    await _update(
        run_id,
        tagged_rows=counts["tagged"],
        type_failed=counts["failed"],
        cost=_cost(status),
        source_to=_cursor_text(last["collect_date"], str(last["content_id"])) if last else "",
    )
    note = f"读取 {len(rows)} 条，写入基础标签 {counts['tagged']} 条，其中判断失败或未对上码表 {counts['failed']} 条"
    if counts["processed"] < len(rows):
        note += (
            f"；{status.get('error_message') or '任务提前停止'}，剩余 {len(rows) - counts['processed']} 条下次接着打"
        )
    return note


async def abandon(run_id: uuid.UUID, message: str) -> None:
    """调度进程中断后收尾：批次记成失败，停掉还在 ai-service 跑的任务。进度没前移，下次从原处重读。"""

    async with SessionLocal() as session:
        run = await repo.get_run(session, run_id)
        if run is None or run.status != "running":
            return
        run.status, run.error_message, run.finished_at = "failed", message[:2000], utcnow()
        ai_run_id = run.type_run_id
        await session.commit()
    if ai_run_id:
        await _stop_quietly(ai_run_id)


async def summary(run_id: uuid.UUID | None) -> dict[str, Any] | None:
    if run_id is None:
        return None
    async with SessionLocal() as session:
        run = await repo.get_run(session, run_id)
        return None if run is None else run_summary(run)


def run_summary(run: PolicyAiRun) -> dict[str, Any]:
    return {
        "status": run.status,
        "stage": run.stage,
        "source_from": run.source_from,
        "source_to": run.source_to,
        "source_rows": run.source_rows,
        "tagged_rows": run.tagged_rows,
        "type_failed": run.type_failed,
        "interpret_rows": run.interpret_rows,
        "interpret_failed": run.interpret_failed,
        "type_run_id": run.type_run_id,
        "interpret_run_id": run.interpret_run_id,
        "opportunity_run_id": run.opportunity_run_id,
        "cost": str(run.cost),
        "note": run.note,
        "error_message": run.error_message,
    }
