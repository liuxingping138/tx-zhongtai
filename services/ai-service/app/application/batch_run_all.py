"""先跑前几行、满意了再跑全部：用同一份数据和发起时冻结的提示词、输出字段、模型、码表新建一个跑全部的任务。

原来要重新选模板、重新上传 Excel，而且模板在这期间改过、重新上线过的话，跑的就不是刚才看过的那一版了。
前面已经答好的行直接沿用，不再重问、不再花钱；没答好的照常问。
"""

from __future__ import annotations

import shutil
from decimal import Decimal
from typing import Any

import anyio
from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.asking import resolve_model
from app.application.audit_emit import enqueue_event
from app.application.batch_output import append_log, copy_answers
from app.application.batch_runs import require, to_dict
from app.application.batch_start import ensure_idle, invalid
from app.application.prompts import require_editable as require_editable_prompt
from app.application.sheets import has_run_input, run_input_head
from app.core import storage
from app.domain.categories import CategoryAccess
from app.domain.models import ACTIVE_STATUSES, RUN_QUEUED, RUN_SOURCE_MANUAL, BatchRun, new_id
from app.domain.templating import build_myid, split_fields
from app.repositories import batch_runs as repo

FROZEN_MODEL = "它是这个任务发起时用的模型，请重新上传数据发起"


def _copy_inputs(source: BatchRun, run_id: str) -> int:
    """数据快照和码表原样复制，前 row_limit 行里答好的抄进新任务。返回沿用了几行。"""

    source_dir, target_dir = storage.run_dir(source.id), storage.run_dir(run_id)
    for name in storage.PROMPT_FILES.values():
        if (source_dir / name).is_file():
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_dir / name, target_dir / name)
    mapping = {build_myid(index): [build_myid(index)] for index in range(source.row_limit)}
    raw = storage.run_file(source.id, "raw")
    copied = copy_answers(raw, storage.run_file(run_id, "raw"), mapping, split_fields(source.output_fields))
    if copied:
        line = (
            f"{format_beijing(utcnow())} 沿用「只跑前 {source.row_limit} 行」那次（任务 {source.id}）"
            f"已答好的 {copied} 条，不再重问"
        )
        append_log(storage.run_file(run_id, "log"), line)
    return copied


async def run_all(session: AsyncSession, actor: Actor, access: CategoryAccess, run_id: str) -> dict[str, Any]:
    source = await require(session, run_id)
    if source.source != RUN_SOURCE_MANUAL or source.row_limit <= 0:
        raise invalid("只有页面发起、只跑了前几行的任务能用同一份数据跑全部")
    if source.status in ACTIVE_STATUSES:
        raise invalid("这次还没跑完，等它结束再跑全部")
    if not await anyio.to_thread.run_sync(has_run_input, storage.run_dir(source.id)):
        raise invalid("这个任务没有保存数据文件（旧系统迁来的），请重新上传数据发起")
    template = await require_editable_prompt(session, access, source.prompt_id, lock=True)
    access.require_edit(source.prompt_category)
    await ensure_idle(session, template)
    model = await resolve_model(session, source.model_id, frozen=FROZEN_MODEL)
    _, rows = await anyio.to_thread.run_sync(run_input_head, storage.run_dir(source.id))
    run = BatchRun(
        id=new_id(),
        prompt_id=source.prompt_id,
        prompt_title=source.prompt_title,
        prompt_category=source.prompt_category,
        prompt_content=source.prompt_content,
        output_fields=source.output_fields,
        model_id=model.id,
        model_name=model.name,
        thinking=source.thinking,
        row_limit=0,
        status=RUN_QUEUED,
        **dict.fromkeys(
            ("done_count", "failed_count", "format_failed_count", "input_tokens", "output_tokens", "cached_tokens"), 0
        ),
        total_count=rows,
        search_calls=0,
        inference_cost=Decimal(0),
        search_cost=Decimal(0),
        cancel_requested=False,
        error_message="",
        created_at=utcnow(),
        created_by_id=actor.id,
        created_by_name=actor.name,
        source=RUN_SOURCE_MANUAL,
        release_no=source.release_no,
        draft_saved_at=source.draft_saved_at,
        input_name=source.input_name,
        service_tier=source.service_tier,
    )
    repo.add(session, run)
    await session.flush()
    reused = await anyio.to_thread.run_sync(_copy_inputs, source, run.id)
    await enqueue_event(
        session,
        event_type="ai.batch_run.started",
        actor=actor,
        category=run.prompt_category,
        target_id=run.id,
        changes={"prompt_id": run.prompt_id, "from_run": source.id, "model_id": model.id, "rows": rows},
        extra={"reused_rows": reused},
    )
    return {**to_dict(run), "reused_rows": reused}
