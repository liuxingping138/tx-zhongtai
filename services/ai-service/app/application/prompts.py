"""提示词模板：增删改、Excel 与码表附件，以及取模板实际使用的码表文本。"""

from __future__ import annotations

from pathlib import PureWindowsPath
from typing import Any

import anyio
from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError
from platform_common.excel import run_excel_parse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import model_configs
from app.application.audit_emit import enqueue_event
from app.application.sheets import code_table_from_sheet, decode_code_table, rows_workbook, sheet_summary
from app.core import storage
from app.core.codebook import fetch_code_table
from app.domain.categories import CategoryAccess, category_name, checked_category
from app.domain.code_tables import checked_code_table, code_digest, code_table_name
from app.domain.models import RUN_SOURCE_SAMPLE, BatchRun, PromptTemplate, TemplateRelease, new_id
from app.domain.releases import release_summary
from app.domain.templating import CODE_TABLE_FIELD, split_fields, template_variables
from app.repositories import batch_runs as run_repo
from app.repositories import prompts as repo
from app.repositories import releases as release_repo

EXCEL_SUFFIX = ".xlsx"
# 码表：文本直接用；Excel 转成一行一条、Tab 分隔的文字再存，运行时和 .txt 一样整份放进 @【上传码表】。
CODE_TEXT_SUFFIXES = (".txt", ".csv")
TITLE_MAX = 255


def sample_summary(template: PromptTemplate, run: BatchRun | None) -> dict[str, Any] | None:
    """最近一次样本试跑；current 表示它跑的就是现在保存的草稿（提示词、输出字段、模型都没再改过）。"""

    if run is None:
        return None
    return {
        "id": run.id,
        "status": run.status,
        "total_count": run.total_count,
        "done_count": run.done_count,
        "failed_count": run.failed_count,
        "format_failed_count": run.format_failed_count,
        # 新建批量任务按它估费用：这份样本每条大概花多少。
        "cost": float(run.inference_cost + run.search_cost),
        "created_at": format_beijing(run.created_at),
        "created_by_name": run.created_by_name,
        "current": sample_current(run, template),
        # 深度思考开没开：开了的回答长得多，按没开的样本估开了的任务会低估。
        "thinking": run.thinking,
    }


def sample_current(run: BatchRun, template: PromptTemplate) -> bool:
    """这次试跑跑的是不是模板现在的草稿。按试跑时记下的草稿保存时间比：换了码表、重传码表文件、换了测试样本
    也会改保存时间，只比提示词、字段、模型会漏掉这些（码表从无换成六级码表，每行多 3.8 万字，预计费用差几十倍）。
    早期的试跑没记保存时间，退回按内容比。"""

    if run.draft_saved_at is not None:
        return run.draft_saved_at == template.updated_at
    return (
        run.prompt_content == template.content
        and run.output_fields == template.output_fields
        and (not template.model_id or run.model_id == template.model_id)
    )


def to_dict(
    template: PromptTemplate,
    model_names: dict[str, str],
    access: CategoryAccess,
    release: TemplateRelease | None = None,
    sample: BatchRun | None = None,
) -> dict[str, Any]:
    return {
        "id": template.id,
        "title": template.title,
        "category": template.category,
        "category_name": category_name(template.category),
        "editable": template.category in access.editable,
        "content": template.content,
        "output_fields": template.output_fields,
        "fields": split_fields(template.output_fields),
        "model_id": template.model_id,
        "model_name": model_names.get(template.model_id, template.model_id),
        "excel_name": template.excel_name,
        "excel_rows": template.excel_rows,
        "excel_headers": list(template.excel_headers or []),
        "code_name": template.code_name,
        "code_table": template.code_table,
        "code_table_name": code_table_name(template.code_table) if template.code_table else "",
        "release": release_summary(template, release, model_names),
        "sample": sample_summary(template, sample),
        "version": template.version,
        "created_at": format_beijing(template.created_at),
        "created_by_name": template.created_by_name,
        "updated_at": format_beijing(template.updated_at),
        "updated_by_name": template.updated_by_name,
    }


def _validated(values: dict[str, Any]) -> dict[str, str]:
    title = str(values.get("title") or "").strip()
    content = str(values.get("content") or "").strip()
    if not title:
        raise ApiError("提示词标题不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if len(title) > TITLE_MAX:
        raise ApiError("标题过长（上限 255 字）", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    # 提示词可以先空着保存：新模板常常先传测试样本、选码表，再照着列名写提示词。试跑和上线时再要求写好。
    return {
        "title": title,
        "category": checked_category(values.get("category")),
        "content": content,
        "output_fields": "|".join(split_fields(str(values.get("output_fields") or ""))),
        "model_id": str(values.get("model_id") or "").strip(),
        "code_table": checked_code_table(values.get("code_table")),
    }


async def to_out(session: AsyncSession, template: PromptTemplate, access: CategoryAccess) -> dict[str, Any]:
    releases = await release_repo.by_ids(session, [template.release_id] if template.release_id else [])
    release = releases.get(template.release_id or "")
    sample = (await run_repo.latest_samples(session, [template.id])).get(template.id)
    return to_dict(template, await model_configs.names(session), access, release, sample)


async def list_prompts(session: AsyncSession, access: CategoryAccess) -> list[dict[str, Any]]:
    """只列当前用户能看到的类型；一个类型都没授权时是空列表，不是全部。"""

    names = await model_configs.names(session)
    items = await repo.list_all(session, categories=access.readable)
    releases = await release_repo.by_ids(session, [item.release_id for item in items if item.release_id])
    samples = await run_repo.latest_samples(session, [item.id for item in items])
    return [to_dict(item, names, access, releases.get(item.release_id or ""), samples.get(item.id)) for item in items]


async def get_prompt(session: AsyncSession, access: CategoryAccess, prompt_id: str) -> dict[str, Any]:
    """看不到这个类型的模板和不存在一样回 404，不透露有这个模板。"""

    template = await require(session, prompt_id)
    if template.category not in access.readable:
        raise NotFoundError("模板不存在或已被删除")
    return await to_out(session, template, access)


async def online(session: AsyncSession, category: str) -> list[PromptTemplate]:
    return await repo.list_online(session, category=category)


async def require(session: AsyncSession, prompt_id: str, *, lock: bool = False) -> PromptTemplate:
    template = await repo.get(session, prompt_id, lock=lock) if storage.ID_PATTERN.fullmatch(prompt_id) else None
    if template is None:
        raise NotFoundError("模板不存在或已被删除")
    return template


async def create_prompt(
    session: AsyncSession, actor: Actor, access: CategoryAccess, values: dict[str, Any]
) -> dict[str, Any]:
    validated = _validated(values)
    access.require_edit(validated["category"])
    now = utcnow()
    template = PromptTemplate(
        id=new_id(),
        **validated,
        created_at=now,
        created_by_id=actor.id,
        created_by_name=actor.name,
        updated_at=now,
        updated_by_id=actor.id,
        updated_by_name=actor.name,
    )
    repo.add(session, template)
    await session.flush()
    await enqueue_event(session, event_type="ai.prompt.created", actor=actor, target_id=template.id)
    return await to_out(session, template, access)


def _touch(template: PromptTemplate, actor: Actor) -> None:
    template.version += 1
    template.updated_at = utcnow()
    template.updated_by_id = actor.id
    template.updated_by_name = actor.name


async def require_editable(
    session: AsyncSession, access: CategoryAccess, prompt_id: str, *, lock: bool = False
) -> PromptTemplate:
    template = await require(session, prompt_id, lock=lock)
    access.require_edit(template.category)
    return template


async def update_prompt(
    session: AsyncSession, actor: Actor, access: CategoryAccess, prompt_id: str, values: dict[str, Any]
) -> dict[str, Any]:
    template = await require_editable(session, access, prompt_id, lock=True)
    if int(values.get("version") or 0) != template.version:
        raise ApiError("模板已被他人修改，请刷新后再保存", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    validated = _validated(values)
    # 改类型等于把模板交给另一条业务线：两边都要有编辑权。
    access.require_edit(validated["category"])
    changes = {key: value for key, value in validated.items() if getattr(template, key) != value}
    for key, value in changes.items():
        setattr(template, key, value)
    _touch(template, actor)
    await enqueue_event(
        session, event_type="ai.prompt.updated", actor=actor, target_id=template.id, changes={"fields": sorted(changes)}
    )
    return await to_out(session, template, access)


async def delete_prompt(session: AsyncSession, actor: Actor, access: CategoryAccess, prompt_id: str) -> None:
    """批量任务发起时已经复制了 Excel 和码表，删模板不影响历史任务和正在跑的任务。"""

    template = await require_editable(session, access, prompt_id, lock=True)
    if template.release_id:
        raise ApiError("模板已上线，定时任务在用它，先下线再删除", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if await run_repo.active_for_prompt(session, prompt_id, sources=(RUN_SOURCE_SAMPLE,)) is not None:
        raise ApiError(
            "这个模板的样本试跑还没结束，等它跑完或先停止再删除", code=ErrorCode.VALIDATION_ERROR, http_status=422
        )
    # 样本试跑只属于这个模板，记录和产物一起清掉，不留孤儿文件；试跑花的钱仍算在费用账单里。
    samples = await run_repo.sample_runs_for_prompt(session, prompt_id)
    now = utcnow()
    for sample in samples:
        run_repo.mark_deleted(sample, now)
    await repo.delete(session, template)
    await enqueue_event(session, event_type="ai.prompt.deleted", actor=actor, target_id=prompt_id)
    await session.flush()
    for folder in (storage.prompt_dir(prompt_id), *(storage.run_dir(sample.id) for sample in samples)):
        await anyio.to_thread.run_sync(storage.remove_tree, folder)


def _check_suffix(filename: str, suffix: str, label: str) -> None:
    if not filename.lower().endswith(suffix):
        raise ApiError(f"{label}只支持 {suffix} 文件", code=ErrorCode.VALIDATION_ERROR, http_status=422)


async def _code_table_text(name: str, content: bytes) -> str:
    lower = name.lower()
    if lower.endswith(EXCEL_SUFFIX):
        return await run_excel_parse(code_table_from_sheet, content)
    if lower.endswith(CODE_TEXT_SUFFIXES):
        return decode_code_table(content)
    raise ApiError("码表只支持 .txt、.csv 或 .xlsx 文件", code=ErrorCode.VALIDATION_ERROR, http_status=422)


def code_download_name(name: str) -> str:
    """码表存的是转好的文字：Excel 上传的下载回去叫 .txt，免得拿 Excel 打开一个文本文件。"""

    return name if name.lower().endswith(CODE_TEXT_SUFFIXES) else f"{PureWindowsPath(name).stem}.txt"


async def upload_file(
    session: AsyncSession,
    actor: Actor,
    access: CategoryAccess,
    prompt_id: str,
    kind: str,
    upload: tuple[str, bytes],
) -> dict[str, Any]:
    """upload 是（浏览器给的文件名，文件内容）。"""

    filename, content = upload
    template = await require_editable(session, access, prompt_id, lock=True)
    # 浏览器可能带上完整路径（C:\fakepath\a.xlsx），斜杠反斜杠都按分隔符处理。
    name = PureWindowsPath(filename or "").name
    if kind == "excel":
        _check_suffix(name, EXCEL_SUFFIX, "Excel ")
        headers, count = await run_excel_parse(sheet_summary, content)
        template.excel_name, template.excel_headers, template.excel_rows = name, headers, count
        payload = content
    else:
        payload = (await _code_table_text(name, content)).encode("utf-8")
        template.code_name, template.code_digest = name, code_digest(payload)
    _touch(template, actor)
    await enqueue_event(
        session, event_type="ai.prompt.file_uploaded", actor=actor, target_id=prompt_id, changes={"kind": kind}
    )
    await session.flush()
    await anyio.to_thread.run_sync(storage.write_atomic, storage.prompt_file(prompt_id, kind), payload)
    return await to_out(session, template, access)


async def save_test_rows(
    session: AsyncSession,
    actor: Actor,
    access: CategoryAccess,
    prompt_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """从数据库取来的测试数据（file_name、headers、rows）存成模板的测试 Excel。

    之后和上传的测试样本一样用：试发选其中一行，样本试跑取前几行；正式的批量任务另外上传数据。
    """

    content = await run_excel_parse(rows_workbook, list(data["headers"]), list(data["rows"]))
    return await upload_file(session, actor, access, prompt_id, "excel", (str(data["file_name"]), content))


async def delete_file(
    session: AsyncSession, actor: Actor, access: CategoryAccess, prompt_id: str, kind: str
) -> dict[str, Any]:
    template = await require_editable(session, access, prompt_id, lock=True)
    if kind == "excel":
        template.excel_name, template.excel_headers, template.excel_rows = "", [], 0
    else:
        template.code_name, template.code_digest = "", ""
    _touch(template, actor)
    await enqueue_event(
        session, event_type="ai.prompt.file_deleted", actor=actor, target_id=prompt_id, changes={"kind": kind}
    )
    await session.flush()
    await anyio.Path(storage.prompt_file(prompt_id, kind)).unlink(missing_ok=True)
    return await to_out(session, template, access)


async def download_file(
    session: AsyncSession, actor: Actor, access: CategoryAccess, prompt_id: str, kind: str
) -> tuple[bytes, str]:
    template = await require(session, prompt_id)
    access.require_read(template.category)
    path = anyio.Path(storage.prompt_file(prompt_id, kind))
    name = template.excel_name if kind == "excel" else template.code_name
    if not name or not await path.is_file():
        raise NotFoundError("文件不存在或已删除")
    if kind == "code":
        name = code_download_name(name)
    await enqueue_event(
        session, event_type="ai.prompt.file_exported", actor=actor, target_id=prompt_id, changes={"kind": kind}
    )
    return await path.read_bytes(), name


CODE_PREVIEW_LINES = 200


def _code_preview(name: str, text: str) -> dict[str, Any]:
    """码表预览：名称、总字数、总行数和前几行。每次提问都把整份放进 @【上传码表】，字数就是每次多送给模型的输入。"""

    lines = text.splitlines()
    return {
        "name": name,
        "chars": len(text),
        "lines": len(lines),
        "head": "\n".join(lines[:CODE_PREVIEW_LINES]),
        "truncated": len(lines) > CODE_PREVIEW_LINES,
    }


async def preview_system_code(key: str) -> dict[str, Any]:
    """系统码表现在的内容（实时从码表服务取）；选码表时就能看，不用先保存模板。"""

    checked = checked_code_table(key)
    if not checked:
        raise ApiError("先选一个系统码表", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return _code_preview(code_table_name(checked), await fetch_code_table(checked))


async def preview_uploaded_code(session: AsyncSession, access: CategoryAccess, prompt_id: str) -> dict[str, Any]:
    template = await require(session, prompt_id)
    access.require_read(template.category)
    path = anyio.Path(storage.prompt_file(template.id, "code"))
    if not template.code_name or not await path.is_file():
        raise NotFoundError("这个模板还没上传码表")
    return _code_preview(template.code_name, await path.read_text(encoding="utf-8"))


def require_code(content: str, code: str | None) -> None:
    """提示词引用了 @【上传码表】却没有码表（或码表是空的）：替换成空字符串照样问，模型拿不到码表瞎答，钱白花。"""

    if CODE_TABLE_FIELD in template_variables(content) and not (code or "").strip():
        raise ApiError(
            f"提示词引用了 @【{CODE_TABLE_FIELD}】，但码表是空的：先上传码表或选一张系统码表",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )


async def code_text(template: PromptTemplate, *, code_table: str | None = None) -> str | None:
    """模板实际用的码表全文：选了系统码表就实时取，否则读上传的码表文件；都没有时为 None。

    code_table 不为 None 时按它选（编辑页上还没保存的选择）：试发要用页面上看到的码表，不能悄悄换成库里存的。
    上传的码表文件是传完就存的，不存在「没保存」。
    """

    key = template.code_table if code_table is None else checked_code_table(code_table)
    if key:
        return await fetch_code_table(key)
    path = anyio.Path(storage.prompt_file(template.id, "code"))
    if template.code_name and await path.is_file():
        return await path.read_text(encoding="utf-8")
    return None
