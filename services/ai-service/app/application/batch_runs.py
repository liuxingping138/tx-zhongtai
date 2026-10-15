"""批量提问任务：发起、列表、进度、停止、删除、下载。真正的执行在 app.worker（独立进程）。"""

from __future__ import annotations

import shutil
from datetime import timedelta
from decimal import Decimal
from typing import Any

import anyio
from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.asking import resolve_model
from app.application.audit_emit import enqueue_event
from app.application.prompts import require as require_prompt
from app.core import storage
from app.core.config import get_settings
from app.domain.models import (
    ACTIVE_STATUSES,
    RUN_CANCELLED,
    RUN_DONE,
    RUN_QUEUED,
    RUN_STOPPING,
    BatchRun,
    new_id,
)
from app.repositories import batch_runs as repo

PAGE_SIZE_MAX = 100
STALE_MESSAGE = "执行进程重启或中断，任务未完成；已跑完的部分可下载原始返回"
_KILO = Decimal(1000)
_PERCENT = 100


def _kilo_tokens(run: BatchRun) -> float:
    return float(((Decimal(run.input_tokens) + Decimal(run.output_tokens)) / _KILO).quantize(Decimal("0.001")))


def _percent(run: BatchRun) -> int:
    if run.status == RUN_DONE:
        return _PERCENT
    return round(run.done_count / run.total_count * _PERCENT) if run.total_count else 0


def _files(run: BatchRun) -> dict[str, bool]:
    return {kind: storage.run_file(run.id, kind).is_file() for kind in storage.RUN_FILES}


def to_dict(run: BatchRun) -> dict[str, Any]:
    active = run.status in ACTIVE_STATUSES
    return {
        "id": run.id,
        "prompt_id": run.prompt_id,
        "prompt_title": run.prompt_title,
        "prompt_content": run.prompt_content,
        "output_fields": run.output_fields,
        "model_id": run.model_id,
        "model_name": run.model_name,
        "thinking": run.thinking,
        "row_limit": run.row_limit,
        "status": run.status,
        "total_count": run.total_count,
        "done_count": run.done_count,
        "failed_count": run.failed_count,
        "percent": _percent(run),
        "total_tokens_kilo": _kilo_tokens(run),
        "inference_cost": float(run.inference_cost),
        "search_cost": float(run.search_cost),
        "search_calls": run.search_calls,
        "error_message": run.error_message,
        "cancel_requested": run.cancel_requested,
        "can_stop": active,
        "can_delete": not active,
        "files": _files(run),
        "created_at": format_beijing(run.created_at),
        "created_by_name": run.created_by_name,
        "started_at": format_beijing(run.started_at),
        "finished_at": format_beijing(run.finished_at),
    }


async def reconcile_stale(session: AsyncSession) -> None:
    """worker 被强杀时来不及收尾，运行中的记录会一直停在 running。按心跳超时纠正，哪个请求先到都能纠正。"""

    cutoff = utcnow() - timedelta(seconds=get_settings().batch_stale_seconds)
    await repo.mark_stale_interrupted(session, cutoff=cutoff, message=STALE_MESSAGE)


async def list_runs(session: AsyncSession, *, page: int, page_size: int) -> dict[str, Any]:
    await reconcile_stale(session)
    size = min(max(page_size, 1), PAGE_SIZE_MAX)
    rows, total = await repo.page(session, offset=(max(page, 1) - 1) * size, limit=size)
    return {"items": [to_dict(run) for run in rows], "total": total, "page": max(page, 1), "page_size": size}


async def require(session: AsyncSession, run_id: str, *, lock: bool = False) -> BatchRun:
    run = await repo.get(session, run_id, lock=lock) if storage.ID_PATTERN.fullmatch(run_id) else None
    if run is None:
        raise NotFoundError("任务不存在或已删除")
    return run


async def get_run(session: AsyncSession, run_id: str) -> dict[str, Any]:
    await reconcile_stale(session)
    return to_dict(await require(session, run_id))


def _snapshot_files(prompt_id: str, run_id: str) -> None:
    target = storage.run_dir(run_id)
    target.mkdir(parents=True, exist_ok=True)
    for kind in ("excel", "code"):
        source = storage.prompt_file(prompt_id, kind)
        if source.is_file():
            shutil.copyfile(source, target / storage.PROMPT_FILES[kind])


async def start_run(session: AsyncSession, actor: Actor, values: dict[str, Any]) -> dict[str, Any]:
    template = await require_prompt(session, str(values.get("prompt_id") or ""), lock=True)
    # 以模板配置的模型为准；模板没配时用发起时页面上选的模型。
    model = resolve_model(template.model_id or str(values.get("model_id") or ""))
    if not template.excel_name or not storage.prompt_file(template.id, "excel").is_file():
        raise ApiError("该模板未上传 Excel，无法批量提问", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    # 同一模板同时只跑一个任务。模板行已加锁，两个人同时点运行只有一个能建出任务。
    await reconcile_stale(session)
    running = await repo.active_for_prompt(session, template.id)
    if running is not None:
        raise ApiError(
            f"该模板已有任务在运行（{running.done_count}/{running.total_count or '?'} 条），请等它结束或先停止",
            code=ErrorCode.VERSION_CONFLICT,
            http_status=409,
        )
    run = BatchRun(
        id=new_id(),
        prompt_id=template.id,
        prompt_title=template.title,
        prompt_content=template.content,
        output_fields=template.output_fields,
        model_id=model.id,
        model_name=model.name,
        thinking=bool(values.get("thinking")) and model.supports_thinking,
        row_limit=max(int(values.get("limit") or 0), 0),
        status=RUN_QUEUED,
        **dict.fromkeys(("total_count", "done_count", "failed_count", "input_tokens", "output_tokens"), 0),
        search_calls=0,
        inference_cost=Decimal(0),
        search_cost=Decimal(0),
        cancel_requested=False,
        error_message="",
        created_at=utcnow(),
        created_by_id=actor.id,
        created_by_name=actor.name,
    )
    repo.add(session, run)
    await session.flush()
    await anyio.to_thread.run_sync(_snapshot_files, template.id, run.id)
    await enqueue_event(
        session,
        event_type="ai.batch_run.started",
        actor=actor,
        target_id=run.id,
        changes={"prompt_id": template.id, "model_id": model.id, "limit": run.row_limit},
    )
    return to_dict(run)


async def stop_run(session: AsyncSession, actor: Actor, run_id: str) -> dict[str, Any]:
    """排队中的直接取消；运行中的只置停止标志，worker 停止提交新请求、等在途请求返回后收尾。"""

    run = await require(session, run_id, lock=True)
    if run.status not in ACTIVE_STATUSES:
        raise ApiError("任务已结束，无需停止", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if run.status == RUN_QUEUED:
        run.status, run.finished_at = RUN_CANCELLED, utcnow()
    else:
        run.status, run.cancel_requested = RUN_STOPPING, True
    await enqueue_event(session, event_type="ai.batch_run.stopped", actor=actor, target_id=run.id)
    return to_dict(run)


async def delete_run(session: AsyncSession, actor: Actor, run_id: str) -> None:
    """运行中不能删：worker 还在写这个目录和这条记录。"""

    await reconcile_stale(session)
    run = await require(session, run_id, lock=True)
    if run.status in ACTIVE_STATUSES:
        raise ApiError("任务仍在运行，请先停止或等它结束再删除", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    await repo.delete(session, run)
    await enqueue_event(session, event_type="ai.batch_run.deleted", actor=actor, target_id=run_id)
    await session.flush()
    await anyio.to_thread.run_sync(storage.remove_tree, storage.run_dir(run_id))


async def download(session: AsyncSession, actor: Actor, run_id: str, kind: str) -> tuple[bytes, str]:
    run = await require(session, run_id)
    path = storage.run_file(run.id, kind)
    if not await anyio.Path(path).is_file():
        raise NotFoundError("文件不存在或尚未生成")
    await enqueue_event(
        session, event_type="ai.batch_run.exported", actor=actor, target_id=run.id, changes={"file": kind}
    )
    title = run.prompt_title.replace("/", "_")[:60]
    return await anyio.Path(path).read_bytes(), f"{title}-{storage.RUN_FILES[kind][1]}"
