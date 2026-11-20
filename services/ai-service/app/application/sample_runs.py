"""样本试跑：用模板草稿把测试样本的前几条整批跑一遍，结果在模板页逐行看，也能下载结果 Excel。

和试发（一次问一行）互补，确认整批效果后再请管理员上线。执行复用批量任务那一套（worker、重试、计费），
来源记为 sample：不进批量任务列表，费用账单里用途是「样本试跑」。

每次试跑按先后叫「第 N 次」，默认和前一次逐行对比（run_compare）：改了提示词之后哪些行修好了、哪些弄坏了，一眼看出。
"""

from __future__ import annotations

import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import anyio
from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import batch_runs, run_compare
from app.application.asking import resolve_model
from app.application.audit_emit import enqueue_event
from app.application.batch_queue import worker_status
from app.application.prompts import code_text, require, require_code, require_editable
from app.application.run_rows import preview
from app.application.sheets import has_run_input
from app.core import storage
from app.domain.categories import CategoryAccess
from app.domain.models import RUN_QUEUED, RUN_SOURCE_SAMPLE, BatchRun, new_id
from app.repositories import batch_runs as repo

ROWS_MAX = 50
ROWS_DEFAULT = 10
# 页面上能挑着看、挑着比的最近几次。
HISTORY_MAX = 20
NO_COMPARE = "none"


def _copy_sample(prompt_id: str, run_id: str, code: str | None) -> None:
    target = storage.run_dir(run_id)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(storage.prompt_file(prompt_id, "excel"), target / storage.PROMPT_FILES["excel"])
    if code is not None:
        storage.write_atomic(target / storage.PROMPT_FILES["code"], code.encode("utf-8"))


async def start(
    session: AsyncSession, actor: Actor, access: CategoryAccess, prompt_id: str, values: dict[str, Any]
) -> dict[str, Any]:
    """跑的是已保存的草稿；页面上有没保存的修改时先保存再试跑。"""

    template = await require_editable(session, access, prompt_id, lock=True)
    if not template.excel_name or not await anyio.Path(storage.prompt_file(template.id, "excel")).is_file():
        raise ApiError("先上传测试样本，再试跑", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if not template.content.strip():
        raise ApiError("提示词还是空的，写好保存后再试跑", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    # 试跑用模板上选定的模型：和上线后定时任务、批量任务用的是同一个，结果才有参考价值。
    if not template.model_id:
        raise ApiError("先在模板上选好模型并保存，再试跑", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    model = await resolve_model(session, template.model_id)
    await batch_runs.reconcile_stale(session)
    running = await repo.active_for_prompt(session, template.id, sources=(RUN_SOURCE_SAMPLE,))
    if running is not None:
        raise ApiError(
            f"上一次样本试跑还没结束（{running.done_count}/{running.total_count} 条），等它跑完或先停止",
            code=ErrorCode.VERSION_CONFLICT,
            http_status=409,
        )
    code = await code_text(template)
    require_code(template.content, code)
    rows = min(max(int(values.get("limit") or ROWS_DEFAULT), 1), ROWS_MAX, template.excel_rows)
    run = BatchRun(
        id=new_id(),
        prompt_id=template.id,
        prompt_title=template.title,
        prompt_category=template.category,
        prompt_content=template.content,
        output_fields=template.output_fields,
        model_id=model.id,
        model_name=model.name,
        thinking=bool(values.get("thinking")) and model.supports_thinking,
        row_limit=rows,
        total_count=rows,
        status=RUN_QUEUED,
        **dict.fromkeys(
            ("done_count", "failed_count", "format_failed_count", "input_tokens", "output_tokens", "cached_tokens"), 0
        ),
        search_calls=0,
        inference_cost=Decimal(0),
        search_cost=Decimal(0),
        cancel_requested=False,
        error_message="",
        created_at=utcnow(),
        created_by_id=actor.id,
        created_by_name=actor.name,
        source=RUN_SOURCE_SAMPLE,
        draft_saved_at=template.updated_at,
        input_name=template.excel_name,
    )
    repo.add(session, run)
    await session.flush()
    await anyio.to_thread.run_sync(_copy_sample, template.id, run.id, code)
    await enqueue_event(
        session,
        event_type="ai.prompt.sample_started",
        actor=actor,
        category=run.prompt_category,
        target_id=template.id,
        changes={"run_id": run.id, "rows": rows, "model_id": model.id},
    )
    return await view(session, access, template.id)


def _brief(run: BatchRun, no: int) -> dict[str, Any]:
    return {
        "no": no,
        "id": run.id,
        "status": run.status,
        "total_count": run.total_count,
        "done_count": run.done_count,
        "failed_count": run.failed_count,
        "format_failed_count": run.format_failed_count,
        "created_at": format_beijing(run.created_at),
    }


def _rows(run: BatchRun) -> dict[str, Any] | None:
    return preview(run) if has_run_input(storage.run_dir(run.id)) else None


def _compared(run: BatchRun, rows: dict[str, Any] | None, previous: BatchRun, no: int) -> dict[str, Any]:
    """和 previous 逐行对比；测试样本换过、或某一次还没有结果时只给出比的是哪一次。"""

    result: dict[str, Any] = {
        "run": _brief(previous, no),
        "same_input": run_compare.same_input(run.id, previous.id),
        "fields_changed": run.output_fields != previous.output_fields,
    }
    earlier = _rows(previous) if rows and result["same_input"] else None
    if rows and earlier:
        result.update(run_compare.compare(rows, earlier))
    return result


async def view(
    session: AsyncSession,
    access: CategoryAccess,
    prompt_id: str,
    *,
    run_id: str | None = None,
    compare_id: str | None = None,
) -> dict[str, Any]:
    """一次样本试跑和它已经跑出来的行（默认最近一次，运行中也给，页面边跑边看），默认和它前一次对比。

    compare_id 指定和哪一次比，NO_COMPARE 表示不比。只能在最近 HISTORY_MAX 次里挑。
    """

    template = await require(session, prompt_id)
    access.require_read(template.category)
    await batch_runs.reconcile_stale(session)
    history, total = await repo.sample_history(session, template.id, limit=HISTORY_MAX)
    numbers = {item.id: total - index for index, item in enumerate(history)}
    if not history:
        return {"run": None, "rows": None, "history": [], "compare": None, "worker_online": True}
    run = next((item for item in history if item.id == run_id), None) if run_id else history[0]
    if run is None:
        raise NotFoundError("试跑记录不存在，或者太早了已不在最近的记录里")
    previous: BatchRun | None = None
    if compare_id and compare_id != NO_COMPARE:
        previous = next((item for item in history if item.id == compare_id and item.id != run.id), None)
        if previous is None:
            raise NotFoundError("要对比的那次试跑不存在")
    elif compare_id != NO_COMPARE:
        older = history[history.index(run) + 1 :]
        previous = older[0] if older else None
    rows = await anyio.to_thread.run_sync(_rows, run)
    same_sample = await anyio.to_thread.run_sync(run_compare.matches_template, run.id, template.id)
    compared = (
        await anyio.to_thread.run_sync(_compared, run, rows, previous, numbers[previous.id]) if previous else None
    )
    return {
        "run": {**batch_runs.to_dict(run), "no": numbers[run.id]},
        "rows": rows,
        "history": [_brief(item, numbers[item.id]) for item in history],
        "compare": compared,
        # 这次试跑的测试样本还是不是模板现在那份：换过的话「试发这一行」不和它比。
        "same_sample": same_sample,
        # 排队中的试跑等不来执行进程时，页面据此说明，而不是一直转圈。
        "worker_online": (await worker_status(session))["online"],
    }


async def retry(
    session: AsyncSession, actor: Actor, access: CategoryAccess, prompt_id: str, run_id: str
) -> dict[str, Any]:
    """只重问这次试跑里失败和没跑到的行，用的还是这次冻结的提示词；改过草稿要看新效果，应该重新试跑。"""

    run = await _own_run(session, prompt_id, run_id)
    await batch_runs.retry_run(session, actor, access, run.id, event_type="ai.prompt.sample_retried", sample=True)
    return await view(session, access, prompt_id, run_id=run.id)


async def _own_run(session: AsyncSession, prompt_id: str, run_id: str) -> BatchRun:
    run = await batch_runs.require(session, run_id, sample=True)
    if run.prompt_id != prompt_id or run.source != RUN_SOURCE_SAMPLE:
        raise NotFoundError("试跑记录不存在")
    return run


async def download(
    session: AsyncSession, actor: Actor, access: CategoryAccess, prompt_id: str, run_id: str, kind: str
) -> tuple[Path, str]:
    """按试跑 ID 下载而不是「最近一次」：点下载的同时有人开了新一轮，拿到的也还是页面上那一轮。"""

    run = await _own_run(session, prompt_id, run_id)
    access.require_read(run.prompt_category)
    path, filename = await batch_runs.run_file_path(run, kind, label="样本试跑")
    await enqueue_event(
        session,
        event_type="ai.prompt.sample_exported",
        actor=actor,
        category=run.prompt_category,
        target_id=prompt_id,
        changes={"run_id": run.id, "file": kind},
    )
    return path, filename


async def stop(session: AsyncSession, actor: Actor, access: CategoryAccess, prompt_id: str) -> dict[str, Any]:
    template = await require_editable(session, access, prompt_id)
    running = await repo.active_for_prompt(session, template.id, sources=(RUN_SOURCE_SAMPLE,))
    if running is None:
        raise ApiError("没有正在进行的样本试跑", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    await batch_runs.stop_run(session, actor, access, running.id, event_type="ai.prompt.sample_stopped", sample=True)
    return await view(session, access, prompt_id)
