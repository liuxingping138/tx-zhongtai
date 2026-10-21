"""提示词模板：增删改、Excel 与码表附件。"""

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
from app.application.sheets import decode_code_table, sheet_summary
from app.core import storage
from app.domain.models import PromptTemplate, new_id
from app.domain.templating import split_fields
from app.repositories import prompts as repo

EXCEL_SUFFIX = ".xlsx"
CODE_SUFFIX = ".txt"
TITLE_MAX = 255


def to_dict(template: PromptTemplate, model_names: dict[str, str]) -> dict[str, Any]:
    return {
        "id": template.id,
        "title": template.title,
        "content": template.content,
        "output_fields": template.output_fields,
        "fields": split_fields(template.output_fields),
        "model_id": template.model_id,
        "model_name": model_names.get(template.model_id, template.model_id),
        "excel_name": template.excel_name,
        "excel_rows": template.excel_rows,
        "excel_headers": list(template.excel_headers or []),
        "code_name": template.code_name,
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
    if not content:
        raise ApiError("提示词内容不能为空", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return {
        "title": title,
        "content": content,
        "output_fields": "|".join(split_fields(str(values.get("output_fields") or ""))),
        "model_id": str(values.get("model_id") or "").strip(),
    }


async def list_prompts(session: AsyncSession) -> list[dict[str, Any]]:
    names = await model_configs.names(session)
    return [to_dict(item, names) for item in await repo.list_all(session)]


async def require(session: AsyncSession, prompt_id: str, *, lock: bool = False) -> PromptTemplate:
    template = await repo.get(session, prompt_id, lock=lock) if storage.ID_PATTERN.fullmatch(prompt_id) else None
    if template is None:
        raise NotFoundError("模板不存在或已被删除")
    return template


async def create_prompt(session: AsyncSession, actor: Actor, values: dict[str, Any]) -> dict[str, Any]:
    now = utcnow()
    template = PromptTemplate(
        id=new_id(),
        **_validated(values),
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
    return to_dict(template, await model_configs.names(session))


def _touch(template: PromptTemplate, actor: Actor) -> None:
    template.version += 1
    template.updated_at = utcnow()
    template.updated_by_id = actor.id
    template.updated_by_name = actor.name


async def update_prompt(session: AsyncSession, actor: Actor, prompt_id: str, values: dict[str, Any]) -> dict[str, Any]:
    template = await require(session, prompt_id, lock=True)
    if int(values.get("version") or 0) != template.version:
        raise ApiError("模板已被他人修改，请刷新后再保存", code=ErrorCode.VERSION_CONFLICT, http_status=409)
    changes = {key: value for key, value in _validated(values).items() if getattr(template, key) != value}
    for key, value in changes.items():
        setattr(template, key, value)
    _touch(template, actor)
    await enqueue_event(
        session, event_type="ai.prompt.updated", actor=actor, target_id=template.id, changes={"fields": sorted(changes)}
    )
    return to_dict(template, await model_configs.names(session))


async def delete_prompt(session: AsyncSession, actor: Actor, prompt_id: str) -> None:
    """批量任务发起时已经复制了 Excel 和码表，删模板不影响历史任务和正在跑的任务。"""

    template = await require(session, prompt_id, lock=True)
    await repo.delete(session, template)
    await enqueue_event(session, event_type="ai.prompt.deleted", actor=actor, target_id=prompt_id)
    await session.flush()
    await anyio.to_thread.run_sync(storage.remove_tree, storage.prompt_dir(prompt_id))


def _check_suffix(filename: str, suffix: str, label: str) -> None:
    if not filename.lower().endswith(suffix):
        raise ApiError(f"{label}只支持 {suffix} 文件", code=ErrorCode.VALIDATION_ERROR, http_status=422)


async def upload_file(
    session: AsyncSession, actor: Actor, prompt_id: str, kind: str, filename: str, content: bytes
) -> dict[str, Any]:
    template = await require(session, prompt_id, lock=True)
    # 浏览器可能带上完整路径（C:\fakepath\a.xlsx），斜杠反斜杠都按分隔符处理。
    name = PureWindowsPath(filename or "").name
    if kind == "excel":
        _check_suffix(name, EXCEL_SUFFIX, "Excel ")
        headers, count = await run_excel_parse(sheet_summary, content)
        template.excel_name, template.excel_headers, template.excel_rows = name, headers, count
        payload = content
    else:
        _check_suffix(name, CODE_SUFFIX, "码表")
        payload = decode_code_table(content).encode("utf-8")
        template.code_name = name
    _touch(template, actor)
    await enqueue_event(
        session, event_type="ai.prompt.file_uploaded", actor=actor, target_id=prompt_id, changes={"kind": kind}
    )
    await session.flush()
    await anyio.to_thread.run_sync(storage.write_atomic, storage.prompt_file(prompt_id, kind), payload)
    return to_dict(template, await model_configs.names(session))


async def delete_file(session: AsyncSession, actor: Actor, prompt_id: str, kind: str) -> dict[str, Any]:
    template = await require(session, prompt_id, lock=True)
    if kind == "excel":
        template.excel_name, template.excel_headers, template.excel_rows = "", [], 0
    else:
        template.code_name = ""
    _touch(template, actor)
    await enqueue_event(
        session, event_type="ai.prompt.file_deleted", actor=actor, target_id=prompt_id, changes={"kind": kind}
    )
    await session.flush()
    await anyio.Path(storage.prompt_file(prompt_id, kind)).unlink(missing_ok=True)
    return to_dict(template, await model_configs.names(session))


async def download_file(session: AsyncSession, actor: Actor, prompt_id: str, kind: str) -> tuple[bytes, str]:
    template = await require(session, prompt_id)
    path = anyio.Path(storage.prompt_file(prompt_id, kind))
    name = template.excel_name if kind == "excel" else template.code_name
    if not name or not await path.is_file():
        raise NotFoundError("文件不存在或已删除")
    await enqueue_event(
        session, event_type="ai.prompt.file_exported", actor=actor, target_id=prompt_id, changes={"kind": kind}
    )
    return await path.read_bytes(), name
