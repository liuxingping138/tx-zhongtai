"""批量任务：发起、列表、进度、停止、重跑、删除、下载。真正的执行在 app.worker（独立进程）。

页面发起的批量任务和定时任务一样，只跑模板的上线版本：业务人员在模板页用样本试好，管理员上线后才用于正式数据。
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import anyio
from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError
from platform_common.filters import Filters
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import releases
from app.application.asking import resolve_model
from app.application.audit_emit import enqueue_event
from app.application.batch_inputs import inspect_upload, snapshot_input
from app.application.prompts import require_editable as require_editable_prompt
from app.application.run_rows import preview as run_rows_preview
from app.application.sheets import has_run_input
from app.core import storage
from app.core.config import get_settings
from app.domain.categories import CategoryAccess, category_name
from app.domain.llm_models import LlmModel
from app.domain.models import (
    ACTIVE_STATUSES,
    RUN_CANCELLED,
    RUN_DONE,
    RUN_QUEUED,
    RUN_SOURCE_MANUAL,
    RUN_STOPPING,
    BatchRun,
    PromptTemplate,
    TemplateRelease,
    new_id,
)
from app.repositories import batch_runs as repo

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
    """重跑要问的行：失败的 + 没跑到的（停止、中断时剩下的）。"""

    return max(run.total_count - run.done_count, 0) + run.failed_count


def _can_retry(run: BatchRun) -> bool:
    # 旧系统迁来的任务没有输入快照，无法重跑。
    ready = run.status not in ACTIVE_STATUSES and run.total_count > 0 and pending_rows(run) > 0
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
        "can_retry": _can_retry(run),
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
    return {"items": [to_dict(run) for run in rows], "total": total, "page": max(page, 1), "page_size": size}


async def filter_options(session: AsyncSession, access: CategoryAccess) -> dict[str, list[str]]:
    """历史里实际出现过的模板名称和操作人；模板删了、改名了，旧名字仍能筛出当时的记录。只取能看到的类型。"""

    return {
        "prompt_title": await repo.distinct_values(session, "prompt_title", categories=access.readable),
        "created_by_name": await repo.distinct_values(session, "created_by_name", categories=access.readable),
    }


async def require(session: AsyncSession, run_id: str, *, lock: bool = False) -> BatchRun:
    run = await repo.get(session, run_id, lock=lock) if storage.ID_PATTERN.fullmatch(run_id) else None
    if run is None:
        raise NotFoundError("任务不存在或已删除")
    return run


async def require_editable(
    session: AsyncSession, access: CategoryAccess, run_id: str, *, lock: bool = False
) -> BatchRun:
    run = await require(session, run_id, lock=lock)
    access.require_edit(run.prompt_category)
    return run


async def get_run(session: AsyncSession, access: CategoryAccess, run_id: str) -> dict[str, Any]:
    await reconcile_stale(session)
    run = await require(session, run_id)
    access.require_read(run.prompt_category)
    return to_dict(run)


async def _plan(
    session: AsyncSession, access: CategoryAccess, prompt_id: str, upload: tuple[str, bytes] | None, *, lock: bool
) -> tuple[PromptTemplate, TemplateRelease, LlmModel, dict[str, Any]]:
    """发起前的全部检查，预检和发起共用：先查不用读文件的（上线、模型、是否在跑），再解析 Excel。"""

    template = await require_editable_prompt(session, access, prompt_id, lock=lock)
    release = await releases.current(session, template, "批量任务")
    model = await resolve_model(session, release.model_id)
    # 同一模板同时只跑一个正式任务。发起时模板行已加锁，两个人同时点运行只有一个能建出任务。
    await reconcile_stale(session)
    running = await repo.active_for_prompt(session, template.id)
    if running is not None:
        raise ApiError(
            f"这个模板已有任务在运行（{running.done_count}/{running.total_count or '?'} 条），请等它结束或先停止",
            code=ErrorCode.VERSION_CONFLICT,
            http_status=409,
        )
    if upload is None:
        raise ApiError("请选择本次任务的数据文件", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return template, release, model, await inspect_upload(release.content, upload)


async def preview_input(
    session: AsyncSession, access: CategoryAccess, prompt_id: str, upload: tuple[str, bytes]
) -> dict[str, Any]:
    """只检查不发起：不调用模型、不建任务、不动模板的测试样本。"""

    _, release, model, summary = await _plan(session, access, prompt_id, upload, lock=False)
    return {**summary, "release_no": release.release_no, "model_name": model.name}


async def start_run(
    session: AsyncSession,
    actor: Actor,
    access: CategoryAccess,
    values: dict[str, Any],
    *,
    upload: tuple[str, bytes] | None = None,
) -> dict[str, Any]:
    template, release, model, summary = await _plan(
        session, access, str(values.get("prompt_id") or ""), upload, lock=True
    )
    # 先取码表：码表服务不可用就不建任务，免得排进队列才发现没有码表。
    code = await releases.release_code(release)
    limit = max(int(values.get("limit") or 0), 0)
    run = BatchRun(
        id=new_id(),
        prompt_id=template.id,
        prompt_title=release.title,
        prompt_category=release.category,
        prompt_content=release.content,
        output_fields=release.output_fields,
        model_id=model.id,
        model_name=model.name,
        thinking=bool(values.get("thinking")) and model.supports_thinking,
        row_limit=limit if 0 < limit < summary["rows"] else 0,
        status=RUN_QUEUED,
        **dict.fromkeys(("done_count", "failed_count", "format_failed_count", "input_tokens", "output_tokens"), 0),
        total_count=min(limit, summary["rows"]) if limit else summary["rows"],
        search_calls=0,
        inference_cost=Decimal(0),
        search_cost=Decimal(0),
        cancel_requested=False,
        error_message="",
        created_at=utcnow(),
        created_by_id=actor.id,
        created_by_name=actor.name,
        source=RUN_SOURCE_MANUAL,
        release_no=release.release_no,
        input_name=summary["name"],
    )
    repo.add(session, run)
    await session.flush()
    await anyio.to_thread.run_sync(snapshot_input, run.id, upload[1] if upload else b"")
    # 码表也按发起时的内容冻结：之后系统码表再改，也不影响这个任务和它的重跑。
    if code is not None:
        await anyio.to_thread.run_sync(
            storage.write_atomic, storage.run_dir(run.id) / storage.PROMPT_FILES["code"], code.encode("utf-8")
        )
    await enqueue_event(
        session,
        event_type="ai.batch_run.started",
        actor=actor,
        target_id=run.id,
        changes={
            "prompt_id": template.id,
            "release_no": release.release_no,
            "model_id": model.id,
            "input": summary["name"],
            "rows": run.total_count,
        },
    )
    return to_dict(run)


async def retry_run(session: AsyncSession, actor: Actor, access: CategoryAccess, run_id: str) -> dict[str, Any]:
    """把已结束的任务重新排队：worker 沿用已成功的行，只问失败和没跑到的，结果合并回本任务，费用累加。"""

    await reconcile_stale(session)
    run = await require_editable(session, access, run_id, lock=True)
    if run.status in ACTIVE_STATUSES:
        raise ApiError("任务仍在运行，结束后才能重跑", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if not await anyio.to_thread.run_sync(_can_retry, run):
        reason = "没有失败或未完成的行" if run.total_count and not pending_rows(run) else _NO_SNAPSHOT
        raise ApiError(reason, code=ErrorCode.VALIDATION_ERROR, http_status=422)
    await resolve_model(session, run.model_id)
    running = await repo.active_for_prompt(session, run.prompt_id)
    if running is not None:
        raise ApiError("该模板已有任务在运行，请等它结束或先停止", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    pending = pending_rows(run)
    run.status, run.cancel_requested, run.error_message = RUN_QUEUED, False, ""
    run.finished_at, run.heartbeat_at = None, None
    await enqueue_event(
        session, event_type="ai.batch_run.retried", actor=actor, target_id=run.id, changes={"rows": pending}
    )
    return to_dict(run)


async def stop_run(
    session: AsyncSession,
    actor: Actor,
    access: CategoryAccess,
    run_id: str,
    *,
    event_type: str = "ai.batch_run.stopped",
) -> dict[str, Any]:
    """排队中的直接取消；运行中的只置停止标志，worker 停止提交新请求、等在途请求返回后收尾。"""

    run = await require_editable(session, access, run_id, lock=True)
    if run.status not in ACTIVE_STATUSES:
        raise ApiError("任务已结束，无需停止", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if run.status == RUN_QUEUED:
        run.status, run.finished_at = RUN_CANCELLED, utcnow()
    else:
        run.status, run.cancel_requested = RUN_STOPPING, True
    await enqueue_event(session, event_type=event_type, actor=actor, target_id=run.id)
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
    """运行中不能删：worker 还在写这个目录和这条记录。"""

    await reconcile_stale(session)
    run = await require_editable(session, access, run_id, lock=True)
    if run.status in ACTIVE_STATUSES:
        raise ApiError("任务仍在运行，请先停止或等它结束再删除", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    await repo.delete(session, run)
    await enqueue_event(session, event_type="ai.batch_run.deleted", actor=actor, target_id=run_id)
    await session.flush()
    await anyio.to_thread.run_sync(storage.remove_tree, storage.run_dir(run_id))


async def download(
    session: AsyncSession, actor: Actor, access: CategoryAccess, run_id: str, kind: str
) -> tuple[bytes, str]:
    run = await require(session, run_id)
    access.require_read(run.prompt_category)
    content, filename = await read_run_file(run, kind)
    await enqueue_event(
        session, event_type="ai.batch_run.exported", actor=actor, target_id=run.id, changes={"file": kind}
    )
    return content, filename


async def read_run_file(run: BatchRun, kind: str, *, label: str = "") -> tuple[bytes, str]:
    """任务产物和下载文件名（模板名-{label}结果.xlsx）；样本试跑的下载也用它。"""

    path = storage.run_file(run.id, kind)
    if not await anyio.Path(path).is_file():
        raise NotFoundError("文件不存在或尚未生成")
    title = run.prompt_title.replace("/", "_")[:60]
    return await anyio.Path(path).read_bytes(), f"{title}-{label}{storage.RUN_FILES[kind][1]}"
