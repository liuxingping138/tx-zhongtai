"""流水线任务：政策服务定时打标时，用模板的上线版本跑一批数据，再把解析后的结果取回去写业务表。

和页面上的批量提问共用同一套执行（worker、重试、计费、历史），区别只在：
- 输入不是上传的 Excel，而是调用方传来的行；落盘成同样的 source.xlsx 快照，执行器不用区分；
- 提示词、输出字段、模型、码表都取上线版本，草稿上的改动不影响生产；
- 按低优档跑，并带费用上限，到上限自动停。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

import anyio
from openpyxl import Workbook
from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError
from platform_common.excel import active_worksheet, append_text_row
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import batch_runs, prompts
from app.application.asking import resolve_model
from app.application.audit_emit import enqueue_event
from app.application.batch_output import read_raw
from app.application.batch_runs import require as require_run
from app.application.batch_runs import to_dict as run_to_dict
from app.application.sheets import read_sheet
from app.core import storage
from app.core.codebook import fetch_code_table
from app.domain.categories import FULL_ACCESS
from app.domain.code_tables import code_table_name
from app.domain.models import ACTIVE_STATUSES, RUN_QUEUED, RUN_SOURCE_PIPELINE, BatchRun, TemplateRelease, new_id
from app.domain.templating import build_myid, parse_fields, split_fields
from app.repositories import batch_runs as run_repo
from app.repositories import releases as release_repo

# 每行带上它，结果按它对回调用方的数据，不依赖行号。
SOURCE_ID = "源ID"
ROWS_MAX = 20_000
# Excel 单元格上限 32767 字，超了打开文件会被截断；调用方应先按自己的规则截断正文。
CELL_MAX = 32_000
PIPELINE_TIER = "flex"


def _invalid(message: str) -> ApiError:
    return ApiError(message, code=ErrorCode.VALIDATION_ERROR, http_status=422)


def _checked_rows(rows: object) -> tuple[list[str], list[dict[str, str]]]:
    if not isinstance(rows, list) or not rows:
        raise _invalid("没有要提问的数据")
    if len(rows) > ROWS_MAX:
        raise _invalid(f"一次最多 {ROWS_MAX} 行")
    headers: list[str] = []
    cleaned: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict) or not str(row.get(SOURCE_ID) or "").strip():
            raise _invalid(f"每行都要有「{SOURCE_ID}」")
        item = {str(key): "" if value is None else str(value) for key, value in row.items()}
        if any(len(value) > CELL_MAX for value in item.values()):
            raise _invalid(f"「{item[SOURCE_ID]}」有单元格超过 {CELL_MAX} 字，请先截断")
        headers.extend(key for key in item if key not in headers)
        cleaned.append(item)
    return headers, cleaned


def _workbook(headers: list[str], rows: list[dict[str, str]]) -> bytes:
    book = Workbook()
    sheet = active_worksheet(book)
    append_text_row(sheet, headers)
    for row in rows:
        append_text_row(sheet, [row.get(name, "") for name in headers])
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _cost_limit(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        limit = Decimal(str(value))
    except InvalidOperation as exc:
        raise _invalid("费用上限不是有效金额") from exc
    if limit <= 0:
        raise _invalid("费用上限必须大于 0")
    return limit


async def _release(session: AsyncSession, prompt_id: str) -> TemplateRelease:
    template = await prompts.require(session, prompt_id, lock=True)
    release = (await release_repo.by_ids(session, [template.release_id] if template.release_id else [])).get(
        template.release_id or ""
    )
    if release is None:
        raise _invalid(f"模板「{template.title}」还没有上线，定时任务只用上线版本")
    return release


async def _release_code(release: TemplateRelease) -> str | None:
    if release.code_table:
        return await fetch_code_table(release.code_table)
    path = anyio.Path(storage.release_code_file(release.id))
    return await path.read_text(encoding="utf-8") if await path.is_file() else None


def _write_snapshot(run_id: str, workbook: bytes, code: str | None) -> None:
    target = storage.run_dir(run_id)
    target.mkdir(parents=True, exist_ok=True)
    storage.write_atomic(target / storage.PROMPT_FILES["excel"], workbook)
    if code is not None:
        storage.write_atomic(target / storage.PROMPT_FILES["code"], code.encode("utf-8"))


async def create(session: AsyncSession, caller: Actor, values: dict[str, Any]) -> dict[str, Any]:
    headers, rows = _checked_rows(values.get("rows"))
    release = await _release(session, str(values.get("prompt_id") or ""))
    model = await resolve_model(session, release.model_id)
    code = await _release_code(release)
    run = BatchRun(
        id=new_id(),
        prompt_id=release.prompt_id,
        prompt_title=release.title,
        prompt_category=release.category,
        prompt_content=release.content,
        output_fields=release.output_fields,
        model_id=model.id,
        model_name=model.name,
        thinking=False,
        row_limit=0,
        status=RUN_QUEUED,
        **dict.fromkeys(
            ("total_count", "done_count", "failed_count", "format_failed_count", "input_tokens", "output_tokens"), 0
        ),
        search_calls=0,
        inference_cost=Decimal(0),
        search_cost=Decimal(0),
        cancel_requested=False,
        error_message="",
        created_at=utcnow(),
        created_by_id=caller.id,
        created_by_name=caller.name,
        source=RUN_SOURCE_PIPELINE,
        release_no=release.release_no,
        service_tier=PIPELINE_TIER,
        cost_limit=_cost_limit(values.get("cost_limit")),
    )
    run_repo.add(session, run)
    await session.flush()
    workbook = await anyio.to_thread.run_sync(_workbook, headers, rows)
    await anyio.to_thread.run_sync(_write_snapshot, run.id, workbook, code)
    await enqueue_event(
        session,
        event_type="ai.batch_run.started",
        actor=caller,
        target_id=run.id,
        changes={"prompt_id": release.prompt_id, "release_no": release.release_no, "rows": len(rows)},
    )
    return run_to_dict(run)


async def status(session: AsyncSession, run_id: str) -> dict[str, Any]:
    return run_to_dict(await require_run(session, run_id))


def _parse_results(run_id: str, output_fields: str) -> list[dict[str, Any]]:
    content = storage.run_dir(run_id).joinpath(storage.PROMPT_FILES["excel"]).read_bytes()
    _, rows = read_sheet(content)
    raw = read_raw(storage.run_file(run_id, "raw"))
    fields = split_fields(output_fields)
    results: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        answer = raw.get(build_myid(index))
        if answer is None:
            results.append({"source_id": row.get(SOURCE_ID, ""), "items": [], "error": "未执行（任务停止或中断）"})
            continue
        items = [] if answer.error else parse_fields(answer.text, fields) or []
        results.append({"source_id": row.get(SOURCE_ID, ""), "items": items, "error": answer.error})
    return results


async def results(session: AsyncSession, run_id: str) -> dict[str, Any]:
    """逐行结果：解析出的字段（一行可能展开成多条）或失败原因。任务结束后才能取，运行中结果还不全。"""

    run = await require_run(session, run_id)
    if run.status in ACTIVE_STATUSES:
        raise ApiError("任务还在运行，结束后再取结果", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    if not storage.run_dir(run.id).joinpath(storage.PROMPT_FILES["excel"]).is_file():
        raise NotFoundError("任务的输入快照不存在")
    items = await anyio.to_thread.run_sync(_parse_results, run.id, run.output_fields)
    return {"run": run_to_dict(run), "items": items}


async def stop(session: AsyncSession, caller: Actor, run_id: str) -> dict[str, Any]:
    """调用方超时或被中断时停掉自己发起的任务，别让它在后台继续花钱。"""

    return await batch_runs.stop_run(session, caller, FULL_ACCESS, run_id)


async def online_templates(session: AsyncSession, category: str) -> list[dict[str, Any]]:
    """可以给定时任务用的模板：已上线的，按类型筛。"""

    items = []
    for template in await prompts.online(session, category):
        release = (await release_repo.by_ids(session, [template.release_id or ""])).get(template.release_id or "")
        if release is None:
            continue
        items.append(
            {
                "prompt_id": template.id,
                "title": release.title,
                "release_no": release.release_no,
                "released_at": format_beijing(release.released_at),
                "model_id": release.model_id,
                "output_fields": split_fields(release.output_fields),
                "code": code_table_name(release.code_table) if release.code_table else release.code_name,
            }
        )
    return items
