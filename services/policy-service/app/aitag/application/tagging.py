"""政策 AI 打标的一批，由任务调度（app.worker.scheduler）调用，一次执行就是一批：

1. 类型判断：从读取进度往后读源政策 → 用上线模板判断政策类型 → 写基础标签 → 进度前移。
2. 政策解读、3. 市场机会：按待办做（见 interpreting），上一批费用到上限没做完的接着做。

模型调用在 ai-service 的 worker 里跑，这里只发起、等待、取结果。每一步按当日剩余额度设费用上限，到上限它自己停。
"""

from __future__ import annotations

import uuid
from typing import Any

import anyio
from platform_common.clock import utcnow

from app.aitag.application import interpreting
from app.aitag.application.pipeline import (
    NOT_RUN,
    ROBOT,
    Spend,
    ask,
    day_start,
    stop_quietly,
    today,
    update_run,
)
from app.aitag.domain import rules
from app.aitag.domain.models import PolicyAiConfig, PolicyAiRun
from app.aitag.repositories import source
from app.aitag.repositories import tagging as repo
from app.common import internal_clients
from app.common.audit_emit import enqueue_event
from app.common.errors import UserFacingError
from app.core.database import SessionLocal
from app.policy.domain.models import BASE_TAG_FIELDS, BaseTag, content_hash

__all__ = ["abandon", "day_start", "policy_type_names", "run_batch", "run_summary", "summary", "today"]


async def policy_type_names() -> list[str]:
    data = await internal_clients.codebook("GET", "/internal/v1/code-tables/policy_types")
    lines = str(data["text"]).split("\n")[1:]
    return [line.split("\t")[0] for line in lines if line.strip()]


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
        # 类型变了，后面两步要按新类型重做。
        existing.interpreted_at = existing.opportunity_at = None
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


async def _save_types(
    run_id: uuid.UUID, rows: list[dict[str, Any]], results: list[dict[str, Any]], known: list[str]
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


def _cursor_text(day: Any, content_id: str) -> str:
    return f"{day.isoformat()} {content_id}".strip()


async def _type_step(run_id: uuid.UUID, config: PolicyAiConfig, spend: Spend) -> str:
    rows = await anyio.to_thread.run_sync(
        source.read_batch, config.cursor_date, config.cursor_content_id, config.batch_size, today()
    )
    if not rows:
        return "类型判断：没有新的源政策"
    contents = await anyio.to_thread.run_sync(source.read_contents, [str(row["content_id"]) for row in rows])
    limit = config.content_max_chars
    prompt_rows = [rules.prompt_row(row, contents.get(str(row["content_id"])), limit) for row in rows]
    known = await policy_type_names()
    await update_run(run_id, stage="typing", source_rows=len(rows))
    status, results = await ask(
        run_id,
        spend,
        prompt_id=config.type_prompt_id,
        rows=prompt_rows,
        caller="政策AI打标·类型判断",
        run_field="type_run_id",
    )
    counts = await _save_types(run_id, rows, results, known)
    last = rows[counts["processed"] - 1] if counts["processed"] else None
    await update_run(
        run_id,
        tagged_rows=counts["tagged"],
        type_failed=counts["failed"],
        source_to=_cursor_text(last["collect_date"], str(last["content_id"])) if last else "",
    )
    note = (
        f"类型判断：读取 {len(rows)} 条，写入基础标签 {counts['tagged']} 条，其中失败或没对上码表 {counts['failed']} 条"
    )
    if counts["processed"] < len(rows):
        reason = status.get("error_message") or "任务提前停止"
        note += f"；{reason}，剩余 {len(rows) - counts['processed']} 条下批接着打"
    return note


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
        note = await _run(run_id, config, Spend(limit=config.daily_cost_limit, before=spent))
        await update_run(run_id, status="success", stage="done", note=note, finished_at=utcnow())
    except Exception as exc:
        message = str(exc) if isinstance(exc, UserFacingError) else f"执行失败（{type(exc).__name__}）"
        await update_run(run_id, status="failed", error_message=message[:2000], finished_at=utcnow())
        raise


async def _run(run_id: uuid.UUID, config: PolicyAiConfig, spend: Spend) -> str:
    if not config.type_prompt_id:
        raise UserFacingError("还没有选「政策类型判断」用的上线模板，请先在任务调度页设置")
    notes: list[str] = []
    steps = [("类型判断", _type_step)]
    if config.interpret_prompt_id:
        steps.append(("政策解读", interpreting.interpret_step))
    if config.opportunity_prompt_id:
        steps.append(("市场机会", interpreting.opportunity_step))
    for name, step in steps:
        if spend.remaining() <= 0:
            used = spend.before + spend.run
            notes.append(f"{name}：今日已花 {used:.2f} 元，达到每日上限 {spend.limit:.2f} 元，留到明天")
            continue
        notes.append(await step(run_id, config, spend))
    return "；".join(notes)


async def abandon(run_id: uuid.UUID, message: str) -> None:
    """调度进程中断后收尾：批次记成失败，停掉还在 ai-service 跑的任务。进度没前移，下次从原处重读。"""

    async with SessionLocal() as session:
        run = await repo.get_run(session, run_id)
        if run is None or run.status != "running":
            return
        run.status, run.error_message, run.finished_at = "failed", message[:2000], utcnow()
        ai_runs = [run.type_run_id, run.interpret_run_id, run.opportunity_run_id]
        await session.commit()
    for ai_run_id in filter(None, ai_runs):
        await stop_quietly(ai_run_id)


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
        "type_cost": str(run.type_cost),
        "interpret_cost": str(run.interpret_cost),
        "opportunity_cost": str(run.opportunity_cost),
        "note": run.note,
        "error_message": run.error_message,
    }
