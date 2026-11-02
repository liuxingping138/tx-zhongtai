"""政策 AI 打标的一批，由任务调度（app.worker.scheduler）调用。三个任务各自执行，一次执行是其中一个任务的一批：

- 类型判断：从读取进度往后读源政策 → 用上线模板判断政策类型 → 写基础标签 → 进度前移。
- 政策解读、市场机会：按待办做（见 interpreting），上一批费用到上限没做完的接着做。

模型调用在 ai-service 的 worker 里跑，这里只发起、等待、取结果。按这个任务当日剩余额度设费用上限，到上限它自己停。
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from http import HTTPStatus
from typing import Any

import anyio
from platform_common.clock import utcnow
from platform_common.errors import ApiError

from app.aitag.application import base_tag_rows, interpreting, retag, scenario_similar
from app.aitag.application.interpreting import untouched
from app.aitag.application.pipeline import (
    NOT_RUN,
    ROBOT,
    Spend,
    ask,
    day_start,
    reused_note,
    stop_quietly,
    today,
    update_run,
)
from app.aitag.domain import rules
from app.aitag.domain.contract import check_template
from app.aitag.domain.models import PolicyAiRun, PolicyAiTask
from app.aitag.domain.tasks import TASKS
from app.aitag.repositories import source
from app.aitag.repositories import tagging as repo
from app.common import internal_clients
from app.common.audit_emit import enqueue_event
from app.common.errors import UserFacingError
from app.core.database import SessionLocal
from app.policy.domain.models import BASE_TAG_FIELDS, content_hash

__all__ = ["abandon", "day_start", "policy_type_names", "run_batch", "run_summary", "summary", "today"]


STAGE_COLUMN = {
    "typing": "type_cost",
    "interpreting": "interpret_cost",
    "opportunity": "opportunity_cost",
    "similar": "scenario_cost",
}
# 读取源库只读到这么多天以前（含）：源库每个采集日的数据第二天才入库完。
SOURCE_SETTLE_DAYS = 2


async def policy_type_names() -> list[str]:
    return await internal_clients.policy_type_names()


async def _save_types(
    run_id: uuid.UUID,
    rows: list[dict[str, Any]],
    results: list[dict[str, Any]],
    known: list[str],
    *,
    retag: bool,
    start: tuple[Any, str] | None = None,
) -> dict[str, int]:
    processed = rules.resume_point(results, NOT_RUN)
    done_rows, done_results = rows[:processed], results[:processed]
    tagged = failed = duplicate = 0
    seen: set[str] = set()
    # 重判后不再是信息化建设类的：它没人核对过的 AI 解读行要清掉，不然解读列表里一直挂着不该有的解读。
    no_longer_interpreted: list[str] = []
    # 和已有基础标签内容一样、没写进去的新政策：记下来，往回重扫时不再花钱问一遍。
    copies: list[str] = []
    async with SessionLocal() as session:
        existing = await repo.base_tags_by_source(session, [str(row["content_id"]) for row in done_rows])
        for row, result in zip(done_rows, done_results, strict=True):
            types, remark = rules.tagging_outcome(result, known)
            failed += 1 if remark else 0
            values = rules.base_tag_values(row, types, remark)
            current = existing.get(str(row["content_id"]))
            if current is not None and retag and result.get("error"):
                # 网络、限流这类失败不是答案：上次判好的类型和解读留着，只记这次失败、出队。
                # 不然一次失败就把类型清空、「是否解读」改成否，没人核对过的 AI 解读也跟着删掉。
                base_tag_rows.note_retag_failed(current, remark)
                continue
            if current is not None and retag:
                values = rules.keep_manual_edits(values, current)
            digest = content_hash(values, BASE_TAG_FIELDS)
            # 内容哈希唯一：手工导入过、同一批里有一模一样的一行（各地转发同一文件）就不重复建；
            # 已有的行改完和另一行一样（原来只差一句失败备注）也不能写：
            # 否则撞唯一约束整批回滚、队列还在，下次又白调一遍模型。
            other = None if digest in seen else await repo.base_tag_by_hash(session, digest)
            if digest in seen or (other is not None and other is not current):
                if current is not None:
                    base_tag_rows.note_duplicate(current)
                    duplicate += 1
                else:
                    copies.append(str(row["content_id"]))
                continue
            seen.add(digest)
            was_interpreted = current is not None and current.need_interpret == "是"
            if base_tag_rows.write(session, current, row, values, force=retag):
                tagged += 1
                if was_interpreted and values["need_interpret"] != "是":
                    no_longer_interpreted.append(str(row["content_id"]))
        await repo.mark_skipped(session, copies, rules.COPY_SKIPPED, utcnow())
        if no_longer_interpreted:
            stale = await repo.ai_interpretations(session, no_longer_interpreted)
            await repo.delete_rows(session, [item for rows_ in stale.values() for item in rows_ if untouched(item)])
        locked = await repo.task(session, "type", lock=True)
        # 重新判断的是列表上点名的旧政策，不动按天读取的进度；这一批跑的时候有人在设置里改了起始日期，
        # 也不能按这一批读到的位置把它改回去。
        moved = start is not None and (locked.cursor_date, locked.cursor_content_id) != start
        if done_rows and not retag and not moved:
            last = done_rows[-1]
            locked.cursor_date, locked.cursor_content_id = last["collect_date"], str(last["content_id"])
        await enqueue_event(
            session,
            event_type="policy.ai_tagging.tagged",
            actor=ROBOT,
            target_id=str(run_id),
            extra={"rows": len(done_rows), "tagged": tagged, "failed": failed, "duplicate": duplicate},
        )
        await session.commit()
    return {"processed": processed, "tagged": tagged, "failed": failed, "duplicate": duplicate}


def _cursor_text(day: Any, content_id: str) -> str:
    return f"{day.isoformat()} {content_id}".strip()


async def _type_step(run_id: uuid.UUID, config: PolicyAiTask, spend: Spend) -> str:
    """有人在列表上点了「重新判断类型」的，这一批先重打它们；没有才按读取进度读新政策。"""

    queued = await retag.type_queue(config.batch_size)
    if queued:
        rows, missing = await retag.read_queued(queued)
        prefix = f"重新判断类型 {len(queued)} 条" + (f"（{missing} 条源库里已找不到，已跳过）" if missing else "")
        return f"{prefix}：{await _tag(run_id, config, spend, rows, retag=True)}" if rows else prefix
    # 只读到前天整天：源库每个采集日的数据第二天才入库，最晚到第二天晚上（实测 10-22 的数据最后一条 10-23 19:48 入库）。
    # 源政策 ID 是哈希、不按入库先后排，读过一天之后再入库、ID 更小的就永远读不到了。
    until = today() - timedelta(days=SOURCE_SETTLE_DAYS)
    start = (config.cursor_date or until, config.cursor_content_id)
    rows = await anyio.to_thread.run_sync(source.read_batch, start[0], start[1], config.batch_size, until)
    if not rows:
        return "没有新的源政策"
    # 打过类型标的跳过：读取进度往回调、重扫某几天补漏时，不能把已经打好的再问一遍模型。
    async with SessionLocal() as session:
        tagged = await repo.tagged_source_ids(session, [str(row["content_id"]) for row in rows])
    fresh = [row for row in rows if str(row["content_id"]) not in tagged]
    if not fresh:
        await _advance_cursor(rows[-1], start)
        return f"读取 {len(rows)} 条，都已经打过类型标，读取进度前移"
    return await _tag(run_id, config, spend, fresh, retag=False, start=start)


async def _advance_cursor(last: dict[str, Any], start: tuple[Any, str]) -> None:
    async with SessionLocal() as session:
        locked = await repo.task(session, "type", lock=True)
        if (locked.cursor_date, locked.cursor_content_id) == start:
            locked.cursor_date, locked.cursor_content_id = last["collect_date"], str(last["content_id"])
        await session.commit()


async def _tag(
    run_id: uuid.UUID,
    config: PolicyAiTask,
    spend: Spend,
    rows: list[dict[str, Any]],
    *,
    retag: bool,
    start: tuple[Any, str] | None = None,
) -> str:
    contents = await anyio.to_thread.run_sync(source.read_contents, [str(row["content_id"]) for row in rows])
    limit = config.content_max_chars
    prompt_rows = [rules.prompt_row(row, contents.get(str(row["content_id"])), limit) for row in rows]
    known = await policy_type_names()
    await update_run(run_id, stage="typing", source_rows=len(rows))
    status, results = await ask(
        run_id,
        spend,
        prompt_id=config.prompt_id,
        rows=prompt_rows,
        caller="政策AI打标·类型判断",
        run_field="type_run_id",
    )
    counts = await _save_types(run_id, rows, results, known, retag=retag, start=start)
    last = rows[counts["processed"] - 1] if counts["processed"] and not retag else None
    await update_run(
        run_id,
        tagged_rows=counts["tagged"],
        type_failed=counts["failed"],
        source_to=_cursor_text(last["collect_date"], str(last["content_id"])) if last else "",
    )
    note = f"读取 {len(rows)} 条{reused_note(status)}，写入基础标签 {counts['tagged']} 条，"
    note += f"其中失败或没对上码表 {counts['failed']} 条"
    if counts["duplicate"]:
        note += f"，{counts['duplicate']} 条重打后和已有记录内容相同、未重复写入"
    if counts["processed"] < len(rows):
        reason = status.get("error_message") or "任务提前停止"
        note += f"；{reason}，剩余 {len(rows) - counts['processed']} 条下批接着打"
    return note


STEPS = {
    "type": _type_step,
    "interpret": interpreting.interpret_step,
    "opportunity": interpreting.opportunity_step,
    "scenario": scenario_similar.similar_step,
}
FIRST_STAGE = {"type": "reading", "interpret": "interpreting", "opportunity": "opportunity", "scenario": "similar"}


async def run_batch(run_id: uuid.UUID, task: str) -> None:
    async with SessionLocal() as session:
        config = await repo.task(session, task)
        spent = await repo.spent_since(session, task, day_start(today()))
        cursor = _cursor_text(config.cursor_date, config.cursor_content_id) if config.cursor_date else ""
        session.add(
            PolicyAiRun(
                id=run_id,
                task=task,
                status="running",
                stage=FIRST_STAGE[task],
                source_from=cursor if task == "type" else "",
                started_at=utcnow(),
            )
        )
        await session.commit()
    try:
        note = await _run(run_id, task, config, Spend(limit=config.daily_cost_limit, before=spent))
        await update_run(run_id, status="success", stage="done", note=note, finished_at=utcnow())
    except ApiError as exc:
        # AI 服务、码表服务明确拒绝（4xx，如模板被下线）：照原话告诉用户，改好之前重试也没用。5xx、连不上照常重试。
        if exc.http_status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            await _fail(run_id, f"执行失败（{type(exc).__name__}）")
            raise
        message = f"AI 服务拒绝执行：{exc.message}"
        await _fail(run_id, message)
        raise UserFacingError(message) from exc
    except Exception as exc:
        await _fail(run_id, str(exc) if isinstance(exc, UserFacingError) else f"执行失败（{type(exc).__name__}）")
        raise


async def _close(run_id: uuid.UUID, message: str, *, only_running: bool) -> list[str]:
    """批次记成失败，返回它发起过的 AI 任务ID。

    失败那一步的花费只记在 cost 里（每次轮询更新），步骤费用列还是 0：补上，当日上限才算得到这笔钱，
    不然重试时额度还是满的，同一批政策再问一遍就超过了每日上限。
    """

    async with SessionLocal() as session:
        run = await repo.get_run(session, run_id)
        if run is None or (only_running and run.status != "running"):
            return []
        run.status, run.error_message, run.finished_at = "failed", message[:2000], utcnow()
        column = STAGE_COLUMN.get(run.stage)
        costs = [run.type_cost, run.interpret_cost, run.opportunity_cost, run.scenario_cost]
        booked = sum((value or Decimal(0) for value in costs), Decimal(0))
        spent = run.cost or Decimal(0)
        if column is not None and spent > booked:
            setattr(run, column, (getattr(run, column) or Decimal(0)) + (spent - booked))
        ai_runs = [run.type_run_id, run.interpret_run_id, run.opportunity_run_id, run.scenario_run_id]
        await session.commit()
    return [ai_run_id for ai_run_id in ai_runs if ai_run_id]


async def _fail(run_id: uuid.UUID, message: str) -> None:
    await _close(run_id, message, only_running=False)


async def check_template_now(task: str, prompt_id: str) -> None:
    """每批开始前按模板现在的上线版本复核一次。换模板时核对过，但同一模板重新上线可能去掉了要写回的字段
    （比如「政策类型名称」），不复核的话每条都记成「没判断出类型」、读取进度照常前移，这批政策就白跑了。"""

    items = await internal_clients.ai("GET", "/internal/v1/online-templates", params={"category": "policy"})
    found = next((item for item in items if item["prompt_id"] == prompt_id), None)
    if found is None:
        raise UserFacingError(f"「{TASKS[task]}」选的模板已下线或不再是政策类，请在任务调度页这个任务的设置里重选")
    variables, fields = list(found.get("variables") or []), list(found.get("output_fields") or [])
    errors = check_template(task, variables, fields, bool(found.get("system_code")))["errors"]
    if errors:
        title = f"「{found['title']}」第 {found.get('release_no')} 版"
        raise UserFacingError(f"{title}不能用于{TASKS[task]}：{'；'.join(errors)}。请改好模板重新上线，或换一个模板")


async def _run(run_id: uuid.UUID, task: str, config: PolicyAiTask, spend: Spend) -> str:
    if not config.prompt_id:
        raise UserFacingError(f"还没有选「{TASKS[task]}」用的上线模板，请在任务调度页这个任务的设置里选")
    if spend.remaining() <= 0:
        return f"今日已花 {spend.before:.2f} 元，达到每日上限 {spend.limit:.2f} 元，留到明天"
    await check_template_now(task, config.prompt_id)
    return await STEPS[task](run_id, config, spend)


async def abandon(run_id: uuid.UUID, message: str) -> None:
    """调度进程中断后收尾：批次记成失败，停掉还在 ai-service 跑的任务。进度没前移，下次从原处重读，
    那批已答好的行沿用（pipeline.ask），不再花钱重问。"""

    for ai_run_id in await _close(run_id, message, only_running=True):
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
        "opportunity_rows": run.opportunity_rows,
        "opportunity_failed": run.opportunity_failed,
        "task": run.task,
        "type_run_id": run.type_run_id,
        "interpret_run_id": run.interpret_run_id,
        "opportunity_run_id": run.opportunity_run_id,
        "cost": str(run.cost),
        "type_cost": str(run.type_cost),
        "interpret_cost": str(run.interpret_cost),
        "opportunity_cost": str(run.opportunity_cost),
        "scenario_run_id": run.scenario_run_id,
        "scenario_rows": run.scenario_rows,
        "scenario_failed": run.scenario_failed,
        "scenario_cost": str(run.scenario_cost),
        "note": run.note,
        "error_message": run.error_message,
    }
