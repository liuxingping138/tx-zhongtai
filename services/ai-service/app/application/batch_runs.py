"""批量任务：列表、进度、停止、重跑、删除、下载；发起在 batch_start。真正的执行在 app.worker（独立进程）。"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import anyio
from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError
from platform_common.filters import Filters
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.asking import resolve_model
from app.application.audit_emit import enqueue_event
from app.application.batch_queue import worker_status
from app.application.run_rows import preview as run_rows_preview
from app.application.sheets import has_run_input
from app.core import storage
from app.core.config import get_settings
from app.domain.categories import CategoryAccess, category_name
from app.domain.models import (
    ACTIVE_STATUSES,
    RUN_CANCELLED,
    RUN_DONE,
    RUN_QUEUED,
    RUN_SOURCE_MANUAL,
    RUN_SOURCE_PIPELINE,
    RUN_SOURCE_SAMPLE,
    RUN_STOPPING,
    BatchRun,
)
from app.repositories import batch_runs as repo
from app.repositories import prompts as prompt_repo

PAGE_SIZE_MAX = 100
STALE_MESSAGE = "执行进程重启或中断，任务未完成；已跑完的部分可下载原始返回"
_KILO = Decimal(1000)
_PERCENT = 100
_NO_SNAPSHOT = "任务没有 Excel 快照（旧系统迁移的任务），无法重跑"


def _kilo_tokens(run: BatchRun) -> float:
    return float(((Decimal(run.input_tokens) + Decimal(run.output_tokens)) / _KILO).quantize(Decimal("0.001")))


def _percent(run: BatchRun) -> int:
    if run.status == RUN_DONE:
        return _PERCENT
    return round(run.done_count / run.total_count * _PERCENT) if run.total_count else 0


def _files(run: BatchRun) -> dict[str, bool]:
    return {kind: storage.run_file(run.id, kind).is_file() for kind in storage.RUN_FILES}


def pending_rows(run: BatchRun) -> int:
    """重跑要问的行：失败的 + 没跑到的（停止、中断时剩下的）。执行进程记了「还没答好的行数」就用它。"""

    if run.open_count is not None:
        return run.open_count
    return max(run.total_count - run.done_count, 0) + run.failed_count


_PIPELINE_NO_RETRY = "定时任务的批次由政策服务取结果，重跑没人消费、只会再花钱；要补跑的政策在基础标签里「重新打标」"


def _can_retry(run: BatchRun) -> bool:
    if run.source == RUN_SOURCE_PIPELINE:
        return False
    # 旧系统迁来的任务没有输入快照，无法重跑。
    ready = run.status not in ACTIVE_STATUSES and run.total_count > 0 and pending_rows(run) > 0
    return ready and has_run_input(storage.run_dir(run.id))


def _can_run_all(run: BatchRun) -> bool:
    """页面发起、只跑了前几行、已经结束的任务，可以用同一份数据跑全部（见 batch_run_all）。"""

    ready = run.source == RUN_SOURCE_MANUAL and run.row_limit > 0 and run.status not in ACTIVE_STATUSES
    return ready and has_run_input(storage.run_dir(run.id))


def to_dict(run: BatchRun) -> dict[str, Any]:
    active = run.status in ACTIVE_STATUSES
    return {
        "id": run.id,
        "prompt_id": run.prompt_id,
        "prompt_title": run.prompt_title,
        "input_name": run.input_name,
        "source": run.source,
        "release_no": run.release_no,
        "draft_saved_at": format_beijing(run.draft_saved_at) if run.draft_saved_at else "",
        "prompt_category": run.prompt_category,
        "prompt_category_name": category_name(run.prompt_category),
        "prompt_content": run.prompt_content,
        "output_fields": run.output_fields,
        "model_id": run.model_id,
        "model_name": run.model_name,
        "thinking": run.thinking,
        "row_limit": run.row_limit,
        "run_mode": "test" if run.row_limit > 0 else "all",
        "status": run.status,
        "total_count": run.total_count,
        "done_count": run.done_count,
        "failed_count": run.failed_count,
        "format_failed_count": run.format_failed_count,
        "pending_count": 0 if active else pending_rows(run),
        # 自动重跑到了第几轮、这一轮重问几条、等待中的话几点开始（见 batch_execute）。
        "retry_round": run.retry_round,
        "round_rows": run.round_rows,
        "round_starts_at": format_beijing(run.round_starts_at) if run.round_starts_at else "",
        "can_retry": _can_retry(run),
        "can_run_all": _can_run_all(run),
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


async def list_runs(
    session: AsyncSession, access: CategoryAccess, *, page: int, page_size: int, filters: Filters | None = None
) -> dict[str, Any]:
    await reconcile_stale(session)
    size = min(max(page_size, 1), PAGE_SIZE_MAX)
    rows, total = await repo.page(
        session, offset=(max(page, 1) - 1) * size, limit=size, filters=filters, categories=access.readable
    )
    return {
        "items": [to_dict(run) for run in rows],
        "total": total,
        "page": max(page, 1),
        "page_size": size,
        "worker_online": (await worker_status(session))["online"],
    }


async def filter_options(session: AsyncSession, access: CategoryAccess) -> dict[str, list[str]]:
    """历史里实际出现过的模板名称和操作人；模板删了、改名了，旧名字仍能筛出当时的记录。只取能看到的类型。"""

    return {
        "prompt_title": await repo.distinct_values(session, "prompt_title", categories=access.readable),
        "created_by_name": await repo.distinct_values(session, "created_by_name", categories=access.readable),
    }


async def require(session: AsyncSession, run_id: str, *, lock: bool = False, sample: bool = False) -> BatchRun:
    """批量任务接口只认正式任务；样本试跑归模板页管（权限是模板的试发档、导出档），sample=True 才认它。

    原来不分来源：拿样本试跑的 ID 就能用批量任务的权限删除、重跑、下载试跑。"""

    run = await repo.get(session, run_id, lock=lock) if storage.ID_PATTERN.fullmatch(run_id) else None
    if run is None or (run.source == RUN_SOURCE_SAMPLE) != sample:
        raise NotFoundError("任务不存在或已删除")
    return run


async def require_editable(
    session: AsyncSession, access: CategoryAccess, run_id: str, *, lock: bool = False, sample: bool = False
) -> BatchRun:
    run = await require(session, run_id, lock=lock, sample=sample)
    access.require_edit(run.prompt_category)
    return run


async def get_run(session: AsyncSession, access: CategoryAccess, run_id: str) -> dict[str, Any]:
    await reconcile_stale(session)
    run = await require(session, run_id)
    access.require_read(run.prompt_category)
    return to_dict(run)


async def retry_run(
    session: AsyncSession,
    actor: Actor,
    access: CategoryAccess,
    run_id: str,
    *,
    event_type: str = "ai.batch_run.retried",
    sample: bool = False,
) -> dict[str, Any]:
    """把已结束的任务重新排队：worker 沿用已成功的行，只问失败和没跑到的，结果合并回本任务，费用累加。
    样本试跑也能重跑，和正式任务各管各的：试跑在跑不挡正式任务重跑，反之亦然。"""

    await reconcile_stale(session)
    run = await require_editable(session, access, run_id, lock=True, sample=sample)
    # 和发起一样先锁模板行：两个人同时重跑同一模板的两个任务、或发起和重跑同时点，都能过「只跑一个」的检查。
    await prompt_repo.get(session, run.prompt_id, lock=True)
    if run.status in ACTIVE_STATUSES:
        raise ApiError("任务仍在运行，结束后才能重跑", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if not await anyio.to_thread.run_sync(_can_retry, run):
        reason = "没有失败或未完成的行" if run.total_count and not pending_rows(run) else _NO_SNAPSHOT
        if run.source == RUN_SOURCE_PIPELINE:
            reason = _PIPELINE_NO_RETRY
        raise ApiError(reason, code=ErrorCode.VALIDATION_ERROR, http_status=422)
    await resolve_model(session, run.model_id, frozen="它是任务发起时冻结的模型，重新启用它或新建任务")
    sources = (RUN_SOURCE_SAMPLE,) if run.source == RUN_SOURCE_SAMPLE else repo.TASK_SOURCES
    running = await repo.active_for_prompt(session, run.prompt_id, sources=sources)
    if running is not None:
        raise ApiError("该模板已有任务在运行，请等它结束或先停止", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    pending = pending_rows(run)
    run.status, run.cancel_requested, run.error_message = RUN_QUEUED, False, ""
    run.finished_at, run.heartbeat_at = None, None
    # 轮次从头算：不然排队期间还显示上次的「第 3 轮：重问 35 条」。
    run.retry_round, run.round_rows, run.round_starts_at = 1, pending, None
    target = run.prompt_id if run.source == RUN_SOURCE_SAMPLE else run.id
    changes: dict[str, Any] = {"rows": pending}
    if run.source == RUN_SOURCE_SAMPLE:
        changes["run_id"] = run.id
    await enqueue_event(
        session, event_type=event_type, actor=actor, category=run.prompt_category, target_id=target, changes=changes
    )
    return to_dict(run)


async def stop_run(
    session: AsyncSession,
    actor: Actor,
    access: CategoryAccess,
    run_id: str,
    *,
    event_type: str = "ai.batch_run.stopped",
    sample: bool = False,
) -> dict[str, Any]:
    """排队中的直接取消；运行中的只置停止标志，worker 停止提交新请求、等在途请求返回后收尾。"""

    run = await require_editable(session, access, run_id, lock=True, sample=sample)
    if run.status not in ACTIVE_STATUSES:
        raise ApiError("任务已结束，无需停止", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if run.status == RUN_QUEUED:
        run.status, run.finished_at = RUN_CANCELLED, utcnow()
    else:
        run.status, run.cancel_requested = RUN_STOPPING, True
    await enqueue_event(session, event_type=event_type, actor=actor, category=run.prompt_category, target_id=run.id)
    return to_dict(run)


async def run_rows(
    session: AsyncSession, access: CategoryAccess, run_id: str, *, failed_only: bool = False
) -> dict[str, Any]:
    run = await require(session, run_id)
    access.require_read(run.prompt_category)
    if not await anyio.to_thread.run_sync(has_run_input, storage.run_dir(run.id)):
        raise NotFoundError("这个任务没有保存输入数据（旧系统迁来的任务），只能下载结果文件")
    return await anyio.to_thread.run_sync(lambda: run_rows_preview(run, failed_only=failed_only))


async def delete_run(session: AsyncSession, actor: Actor, access: CategoryAccess, run_id: str) -> None:
    """运行中不能删：worker 还在写这个目录和这条记录。删掉的是列表里的记录和产物文件，花的钱仍算在费用账单里。"""

    await reconcile_stale(session)
    run = await require_editable(session, access, run_id, lock=True)
    if run.status in ACTIVE_STATUSES:
        raise ApiError("任务仍在运行，请先停止或等它结束再删除", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    repo.mark_deleted(run, utcnow())
    await enqueue_event(
        session, event_type="ai.batch_run.deleted", actor=actor, category=run.prompt_category, target_id=run_id
    )
    await session.flush()
    await anyio.to_thread.run_sync(storage.remove_tree, storage.run_dir(run_id))


async def download(
    session: AsyncSession, actor: Actor, access: CategoryAccess, run_id: str, kind: str
) -> tuple[Path, str]:
    run = await require(session, run_id)
    access.require_read(run.prompt_category)
    path, filename = await run_file_path(run, kind)
    await enqueue_event(
        session,
        event_type="ai.batch_run.exported",
        actor=actor,
        category=run.prompt_category,
        target_id=run.id,
        changes={"file": kind},
    )
    return path, filename


async def run_file_path(run: BatchRun, kind: str, *, label: str = "") -> tuple[Path, str]:
    """任务产物的路径和下载文件名（模板名-{label}结果.xlsx）；样本试跑的下载也用它。

    给路径、由响应边读边发，不整份读进内存：原始返回每行带整段提问，大任务一份就有几个 G，
    在单 worker 的 HTTP 进程里读一次就可能把它撑爆，试发、对话一起中断。
    """

    path = storage.run_file(run.id, kind)
    if not await anyio.Path(path).is_file():
        raise NotFoundError("文件不存在或尚未生成")
    title = run.prompt_title.replace("/", "_")[:60]
    return path, f"{title}-{label}{storage.RUN_FILES[kind][1]}"
