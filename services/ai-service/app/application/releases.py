"""模板上线：把当前模板冻结成一版，定时任务只跑上线版本（批量任务可选上线版本或草稿）。之后再改模板只改草稿，重新上线才生效。"""

from __future__ import annotations

import shutil
from typing import Any

import anyio
from platform_common.actors import Actor
from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import prompts
from app.application.asking import resolve_model
from app.application.audit_emit import enqueue_event
from app.core import storage
from app.core.codebook import fetch_code_table
from app.domain.categories import CategoryAccess
from app.domain.code_tables import code_table_name
from app.domain.models import PromptTemplate, TemplateRelease, new_id
from app.domain.templating import split_fields
from app.repositories import releases as repo


def _invalid(message: str) -> ApiError:
    return ApiError(message, code=ErrorCode.VALIDATION_ERROR, http_status=422)


async def _check_publishable(session: AsyncSession, template: PromptTemplate) -> None:
    """定时任务没人盯着：上线前把会让它整批跑废的情况挡住。"""

    if not template.content.strip():
        raise _invalid("上线前要写好提示词")
    if not split_fields(template.output_fields):
        raise _invalid("上线前要设置新增输出字段，否则结果解析不出任何字段")
    if not template.model_id:
        raise _invalid("上线前要在模板上选定模型，定时任务不会替你挑")
    await resolve_model(session, template.model_id)
    prompts.require_code(template.content, await prompts.code_text(template))


async def current(session: AsyncSession, template: PromptTemplate, purpose: str) -> TemplateRelease:
    """模板正在生效的上线版本；没上线就拒绝，purpose 写清楚是谁要用（定时任务 / 批量任务）。"""

    release = (await repo.by_ids(session, [template.release_id] if template.release_id else [])).get(
        template.release_id or ""
    )
    if release is None:
        raise _invalid(f"模板「{template.title}」还没有上线，{purpose}只用上线版本，请管理员先上线")
    return release


async def release_code(release: TemplateRelease) -> str | None:
    """上线版本用的码表全文：系统码表实时取（取不到报 503），上传的码表读上线时复制的那份。"""

    if release.code_table:
        return await fetch_code_table(release.code_table)
    path = anyio.Path(storage.release_code_file(release.id))
    return await path.read_text(encoding="utf-8") if await path.is_file() else None


def _copy_code_file(prompt_id: str, release_id: str) -> None:
    source = storage.prompt_file(prompt_id, "code")
    if source.is_file():
        target = storage.release_code_file(release_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


async def publish(
    session: AsyncSession, actor: Actor, access: CategoryAccess, prompt_id: str, *, version: int | None = None
) -> dict[str, Any]:
    template = await prompts.require(session, prompt_id, lock=True)
    access.require_read(template.category)
    if version is not None and version != template.version:
        raise ApiError(
            "草稿在你核对之后又被修改过（提示词、字段或文件），请刷新看清改动再上线",
            code=ErrorCode.VERSION_CONFLICT,
            http_status=409,
        )
    await _check_publishable(session, template)
    release = TemplateRelease(
        id=new_id(),
        prompt_id=template.id,
        release_no=await repo.last_no(session, template.id) + 1,
        title=template.title,
        category=template.category,
        content=template.content,
        output_fields=template.output_fields,
        model_id=template.model_id,
        code_table=template.code_table,
        code_name="" if template.code_table else template.code_name,
        code_digest="" if template.code_table else template.code_digest,
        released_at=utcnow(),
        released_by_id=actor.id,
        released_by_name=actor.name,
    )
    repo.add(session, release)
    template.release_id = release.id
    await session.flush()
    if not template.code_table and template.code_name:
        await anyio.to_thread.run_sync(_copy_code_file, template.id, release.id)
    await enqueue_event(
        session,
        event_type="ai.prompt.released",
        actor=actor,
        target_id=template.id,
        changes={"release_no": release.release_no},
    )
    return await prompts.to_out(session, template, access)


async def take_offline(session: AsyncSession, actor: Actor, access: CategoryAccess, prompt_id: str) -> dict[str, Any]:
    """下线只是不再有生效版本；历史版本保留，可随时重新上线。"""

    template = await prompts.require(session, prompt_id, lock=True)
    access.require_read(template.category)
    if not template.release_id:
        raise _invalid("模板还没有上线")
    template.release_id = None
    await enqueue_event(session, event_type="ai.prompt.offlined", actor=actor, target_id=template.id)
    return await prompts.to_out(session, template, access)


async def list_releases(session: AsyncSession, access: CategoryAccess, prompt_id: str) -> list[dict[str, Any]]:
    template = await prompts.require(session, prompt_id)
    access.require_read(template.category)
    return [
        {
            "id": item.id,
            "release_no": item.release_no,
            "current": item.id == template.release_id,
            "title": item.title,
            "content": item.content,
            "output_fields": item.output_fields,
            "model_id": item.model_id,
            "code": code_table_name(item.code_table) if item.code_table else item.code_name,
            "released_at": format_beijing(item.released_at),
            "released_by_name": item.released_by_name,
        }
        for item in await repo.list_for_prompt(session, prompt_id)
    ]
