"""样本试跑：用模板草稿把测试样本的前几条整批跑一遍，结果在模板页逐行看，也能下载结果 Excel。

和试发（只问第一行）互补，确认整批效果后再请管理员上线。执行复用批量任务那一套（worker、重试、计费），
来源记为 sample：不进批量任务列表，费用账单里用途是「样本试跑」。
"""

from __future__ import annotations

import shutil
from decimal import Decimal
from typing import Any

import anyio
from platform_common.actors import Actor
from platform_common.clock import utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import batch_runs
from app.application.asking import resolve_model
from app.application.audit_emit import enqueue_event
from app.application.prompts import code_text, require, require_editable
from app.application.run_rows import preview
from app.application.sheets import has_run_input
from app.core import storage
from app.domain.categories import CategoryAccess
from app.domain.models import RUN_QUEUED, RUN_SOURCE_SAMPLE, BatchRun, new_id
from app.repositories import batch_runs as repo

ROWS_MAX = 50
ROWS_DEFAULT = 10


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
        **dict.fromkeys(("done_count", "failed_count", "format_failed_count", "input_tokens", "output_tokens"), 0),
        search_calls=0,
        inference_cost=Decimal(0),
        search_cost=Decimal(0),
        cancel_requested=False,
        error_message="",
        created_at=utcnow(),
        created_by_id=actor.id,
        created_by_name=actor.name,
        source=RUN_SOURCE_SAMPLE,
        input_name=template.excel_name,
    )
    repo.add(session, run)
    await session.flush()
    await anyio.to_thread.run_sync(_copy_sample, template.id, run.id, code)
    await enqueue_event(
        session,
        event_type="ai.prompt.sample_started",
        actor=actor,
        target_id=template.id,
        changes={"run_id": run.id, "rows": rows, "model_id": model.id},
    )
    return {"run": batch_runs.to_dict(run), "rows": None}


async def latest(session: AsyncSession, access: CategoryAccess, prompt_id: str) -> dict[str, Any]:
    """最近一次样本试跑和它已经跑出来的行；运行中也给，页面边跑边看。"""

    template = await require(session, prompt_id)
    access.require_read(template.category)
    await batch_runs.reconcile_stale(session)
    run = (await repo.latest_samples(session, [template.id])).get(template.id)
    if run is None:
        return {"run": None, "rows": None}
    ready = await anyio.to_thread.run_sync(has_run_input, storage.run_dir(run.id))
    rows = await anyio.to_thread.run_sync(lambda: preview(run)) if ready else None
    return {"run": batch_runs.to_dict(run), "rows": rows}


async def download(
    session: AsyncSession, actor: Actor, access: CategoryAccess, prompt_id: str, run_id: str, kind: str
) -> tuple[bytes, str]:
    """按试跑 ID 下载而不是「最近一次」：点下载的同时有人开了新一轮，拿到的也还是页面上那一轮。"""

    run = await batch_runs.require(session, run_id)
    if run.prompt_id != prompt_id or run.source != RUN_SOURCE_SAMPLE:
        raise NotFoundError("试跑记录不存在")
    access.require_read(run.prompt_category)
    content, filename = await batch_runs.read_run_file(run, kind, label="样本试跑")
    await enqueue_event(
        session,
        event_type="ai.prompt.sample_exported",
        actor=actor,
        target_id=prompt_id,
        changes={"run_id": run.id, "file": kind},
    )
    return content, filename


async def stop(session: AsyncSession, actor: Actor, access: CategoryAccess, prompt_id: str) -> dict[str, Any]:
    template = await require_editable(session, access, prompt_id)
    running = await repo.active_for_prompt(session, template.id, sources=(RUN_SOURCE_SAMPLE,))
    if running is None:
        raise ApiError("没有正在进行的样本试跑", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    await batch_runs.stop_run(session, actor, access, running.id, event_type="ai.prompt.sample_stopped")
    return await latest(session, access, prompt_id)
