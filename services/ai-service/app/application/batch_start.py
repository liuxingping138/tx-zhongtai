"""发起批量任务：选跑模板的上线版本，或者已保存的草稿。

业务人员调好模板就能拿本地 Excel 跑，不用等管理员上线；定时任务没人盯着，仍然只跑上线版本（见 pipeline_runs）。
两种都在发起时把提示词、输出字段、模型和码表冻结进任务：之后改模板、重新上线、删模板都不影响它。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import anyio
from platform_common.actors import Actor
from platform_common.clock import utcnow
from platform_common.errors import ApiError, ErrorCode
from platform_common.excel import run_excel_parse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import releases
from app.application.asking import RELEASE_MODEL_DISABLED, resolve_model
from app.application.audit_emit import enqueue_event
from app.application.batch_inputs import blank_input, inspect_upload, snapshot_input
from app.application.batch_runs import reconcile_stale, to_dict
from app.application.prompts import code_text, require_code
from app.application.prompts import require_editable as require_editable_prompt
from app.application.sheets import CELL_MAX, rows_workbook
from app.core import storage
from app.core.config import get_settings
from app.domain.categories import CategoryAccess
from app.domain.llm_models import LlmModel
from app.domain.models import RUN_QUEUED, RUN_SOURCE_MANUAL, BatchRun, PromptTemplate, TemplateRelease, new_id
from app.repositories import batch_runs as repo

VERSION_RELEASE = "release"
VERSION_DRAFT = "draft"


def invalid(message: str) -> ApiError:
    return ApiError(message, code=ErrorCode.VALIDATION_ERROR, http_status=422)


@dataclass(frozen=True)
class _Spec:
    """这次任务要跑的内容：模板的上线版本（release 不为空），或者已保存的草稿（draft_saved_at 不为空）。"""

    title: str
    category: str
    content: str
    output_fields: str
    model: LlmModel
    release: TemplateRelease | None = None
    draft_saved_at: datetime | None = None


async def _spec(session: AsyncSession, template: PromptTemplate, version: str) -> _Spec:
    if version == VERSION_DRAFT:
        if not template.content.strip():
            raise invalid("草稿的提示词还是空的，写好保存后再跑")
        if not template.model_id:
            raise invalid("草稿还没选模型，先在模板上选好模型并保存")
        model = await resolve_model(session, template.model_id)
        return _Spec(
            template.title,
            template.category,
            template.content,
            template.output_fields,
            model,
            draft_saved_at=template.updated_at,
        )
    if not template.release_id:
        raise invalid(f"模板「{template.title}」还没有上线，可以选「当前草稿」跑，或请管理员先上线")
    release = await releases.current(session, template, "批量任务")
    model = await resolve_model(session, release.model_id, frozen=RELEASE_MODEL_DISABLED)
    return _Spec(release.title, release.category, release.content, release.output_fields, model, release=release)


async def _code(template: PromptTemplate, spec: _Spec) -> str | None:
    """码表全文，发起时冻结进任务目录：上线版本用上线时那份，草稿用模板现在选的（系统码表实时取）。"""

    code = await releases.release_code(spec.release) if spec.release else await code_text(template)
    require_code(spec.content, code)
    return code


async def ensure_idle(session: AsyncSession, template: PromptTemplate) -> None:
    """同一模板同时只跑一个正式任务。调用方已锁模板行，两个人同时点运行只有一个能建出任务。"""

    await reconcile_stale(session)
    running = await repo.active_for_prompt(session, template.id)
    if running is not None:
        raise ApiError(
            f"这个模板已有任务在运行（{running.done_count}/{running.total_count or '?'} 条），请等它结束或先停止",
            code=ErrorCode.VERSION_CONFLICT,
            http_status=409,
        )


async def _check_ready(
    session: AsyncSession,
    access: CategoryAccess,
    prompt_id: str,
    *,
    version: str,
    lock: bool,
) -> tuple[PromptTemplate, _Spec]:
    """发起前的库内检查：版本、模型、类型编辑权与是否空闲。lock=False 无锁预检，lock=True 写库前加行锁防并发。"""

    template = await require_editable_prompt(session, access, prompt_id, lock=lock)
    spec = await _spec(session, template, version)
    # 任务记在跑的那一版的类型下（上线后改了模板类型、没重新上线时，和模板现在的类型不一样）：
    # 这一类也得能编辑，不然发起人看不到、停不了自己刚发起的任务，钱也记到别的类型名下。
    access.require_edit(spec.category)
    await ensure_idle(session, template)
    return template, spec


async def preview_input(
    session: AsyncSession,
    access: CategoryAccess,
    prompt_id: str,
    upload: tuple[str, bytes],
    *,
    version: str = VERSION_RELEASE,
) -> dict[str, Any]:
    """只检查不发起：不调用模型、不建任务、不动模板的测试样本。"""

    _, spec = await _check_ready(session, access, prompt_id, version=version, lock=False)
    # 先释放只读事务再解析 Excel，避免大表格解析期间占着数据库连接。
    await session.commit()
    summary = await inspect_upload(spec.content, upload)
    release_no = spec.release.release_no if spec.release else None
    return {**summary, "version": version, "release_no": release_no, "model_name": spec.model.name}


async def input_template(
    session: AsyncSession, access: CategoryAccess, prompt_id: str, *, version: str = VERSION_RELEASE
) -> tuple[bytes, str]:
    """新建任务时下载的空白数据表：按要跑的那一版要的列，业务人员照着填好再上传。不看模型和是否在跑，只是一张表头。"""

    template = await require_editable_prompt(session, access, prompt_id)
    if version == VERSION_DRAFT:
        content, label = template.content, "草稿"
    else:
        release = await releases.current(session, template, "批量任务")
        access.require_read(release.category)
        content, label = release.content, f"第{release.release_no}版"
    title = template.title.replace("/", "_")[:60]
    return await blank_input(content), f"{title}-{label}数据模板.xlsx"


async def start_run(
    session: AsyncSession,
    actor: Actor,
    access: CategoryAccess,
    values: dict[str, Any],
    *,
    upload: tuple[str, bytes] | None = None,
) -> dict[str, Any]:
    version = str(values.get("version") or VERSION_RELEASE)
    prompt_id = str(values.get("prompt_id") or "")
    template, spec = await _check_ready(session, access, prompt_id, version=version, lock=False)
    if upload is None:
        raise invalid("请选择本次任务的数据文件")
    # 放掉只读事务后再解析 Excel 与请求码表服务（对齐 pipeline_runs），不在 FOR UPDATE 锁内做长耗时外部 I/O。
    await session.commit()
    summary = await inspect_upload(spec.content, upload)
    # 先取码表：码表服务不可用就不建任务，免得排进队列才发现没有码表。
    code = await _code(template, spec)
    template, locked_spec = await _check_ready(session, access, prompt_id, version=version, lock=True)
    if locked_spec.content != spec.content or (
        locked_spec.release is not None and spec.release is not None and locked_spec.release.id != spec.release.id
    ):
        raise ApiError(
            "模板内容或上线版本刚刚被修改，请刷新后重新发起", code=ErrorCode.VERSION_CONFLICT, http_status=409
        )
    spec = locked_spec
    limit = max(int(values.get("limit") or 0), 0)
    model = spec.model
    run = BatchRun(
        id=new_id(),
        prompt_id=template.id,
        prompt_title=spec.title,
        prompt_category=spec.category,
        prompt_content=spec.content,
        output_fields=spec.output_fields,
        model_id=model.id,
        model_name=model.name,
        thinking=bool(values.get("thinking")) and model.supports_thinking,
        row_limit=limit if 0 < limit < summary["rows"] else 0,
        status=RUN_QUEUED,
        **dict.fromkeys(
            ("done_count", "failed_count", "format_failed_count", "input_tokens", "output_tokens", "cached_tokens"), 0
        ),
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
        release_no=spec.release.release_no if spec.release else None,
        draft_saved_at=spec.draft_saved_at,
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
        category=run.prompt_category,
        target_id=run.id,
        changes={
            "prompt_id": template.id,
            "version": version,
            "release_no": run.release_no,
            "model_id": model.id,
            "input": summary["name"],
            "rows": run.total_count,
        },
    )
    return to_dict(run)


# 从政策库取数时一次最多这么多字（表头加全部单元格）。政策服务取样本按同一个数截（samples.CHARS_BUDGET），
# 这里再拦一次，超了在生成 Excel 之前就说清楚，不白占线程池。UTF-8 一个汉字 3 字节，远低于网关 20MB 的请求上限。
ROWS_CHARS_MAX = 5_000_000


def _check_rows(data: dict[str, Any]) -> int:
    """生成 Excel 前先查：总字数不超上限、每行不比表头多列。返回超过 Excel 单元格上限、会被截断的格数。"""

    headers, rows = list(data["headers"]), list(data["rows"])
    total = sum(len(name) for name in headers) + sum(len(cell) for row in rows for cell in row)
    if total > ROWS_CHARS_MAX:
        raise ApiError(
            f"抽取的数据共 {total // 10_000} 万字，超过单次上限 {ROWS_CHARS_MAX // 10_000} 万字，"
            "请减少条数或截取正文后重试",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=413,
        )
    wide = next((index for index, row in enumerate(rows, start=1) if len(row) > len(headers)), 0)
    if wide:
        raise invalid(f"第 {wide} 行比表头多出几列，数据和表头对不上")
    return sum(1 for row in rows for cell in row if len(cell) > CELL_MAX)


async def _rows_upload(data: dict[str, Any]) -> tuple[str, bytes]:
    content = await run_excel_parse(rows_workbook, list(data["headers"]), list(data["rows"]), "数据")
    max_bytes = get_settings().upload_max_bytes
    if len(content) > max_bytes:
        raise ApiError(
            f"抽取的数据超过单次上限（{max_bytes // (1024 * 1024)}MB），请减少条数后重试",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=413,
        )
    return str(data["file_name"]), content


def truncation_warning(cells: int) -> str:
    if not cells:
        return ""
    return (
        f"有 {cells} 个单元格超过 Excel 单元格上限 {CELL_MAX:,} 字，批量任务按 Excel 跑，这些格子会被截断；"
        "定时打标不经 Excel、不截断，要对比结果请把正文改成截取"
    )


async def preview_rows(
    session: AsyncSession,
    access: CategoryAccess,
    prompt_id: str,
    data: dict[str, Any],
    *,
    version: str = VERSION_RELEASE,
) -> dict[str, Any]:
    """从数据库取数后的预检：转为 Excel 复用同一套列校验与行数统计，并说明有没有格子会被截断。"""

    cells = _check_rows(data)
    summary = await preview_input(session, access, prompt_id, await _rows_upload(data), version=version)
    return {**summary, "truncated_cells": cells, "warning": truncation_warning(cells)}


async def start_run_from_rows(
    session: AsyncSession,
    actor: Actor,
    access: CategoryAccess,
    values: dict[str, Any],
    data: dict[str, Any],
) -> dict[str, Any]:
    """从数据库取数发起离线批量验证任务（不写回政策库，产物同手工上传任务）。"""

    _check_rows(data)
    return await start_run(session, actor, access, values, upload=await _rows_upload(data))
