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
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import releases
from app.application.asking import RELEASE_MODEL_DISABLED, resolve_model
from app.application.audit_emit import enqueue_event
from app.application.batch_inputs import blank_input, inspect_upload, snapshot_input
from app.application.batch_runs import reconcile_stale, to_dict
from app.application.prompts import code_text
from app.application.prompts import require_editable as require_editable_prompt
from app.core import storage
from app.domain.categories import CategoryAccess
from app.domain.llm_models import LlmModel
from app.domain.models import RUN_QUEUED, RUN_SOURCE_MANUAL, BatchRun, PromptTemplate, TemplateRelease, new_id
from app.repositories import batch_runs as repo

VERSION_RELEASE = "release"
VERSION_DRAFT = "draft"


def _invalid(message: str) -> ApiError:
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
            raise _invalid("草稿的提示词还是空的，写好保存后再跑")
        if not template.model_id:
            raise _invalid("草稿还没选模型，先在模板上选好模型并保存")
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
        raise _invalid(f"模板「{template.title}」还没有上线，可以选「当前草稿」跑，或请管理员先上线")
    release = await releases.current(session, template, "批量任务")
    model = await resolve_model(session, release.model_id, frozen=RELEASE_MODEL_DISABLED)
    return _Spec(release.title, release.category, release.content, release.output_fields, model, release=release)


async def _code(template: PromptTemplate, spec: _Spec) -> str | None:
    """码表全文，发起时冻结进任务目录：上线版本用上线时那份，草稿用模板现在选的（系统码表实时取）。"""

    return await releases.release_code(spec.release) if spec.release else await code_text(template)


async def _plan(
    session: AsyncSession,
    access: CategoryAccess,
    prompt_id: str,
    upload: tuple[str, bytes] | None,
    *,
    version: str,
    lock: bool,
) -> tuple[PromptTemplate, _Spec, dict[str, Any]]:
    """发起前的全部检查，预检和发起共用：先查不用读文件的（版本、模型、是否在跑），再解析 Excel。"""

    template = await require_editable_prompt(session, access, prompt_id, lock=lock)
    spec = await _spec(session, template, version)
    # 任务记在跑的那一版的类型下（上线后改了模板类型、没重新上线时，和模板现在的类型不一样）：
    # 这一类也得能编辑，不然发起人看不到、停不了自己刚发起的任务，钱也记到别的类型名下。
    access.require_edit(spec.category)
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
        raise _invalid("请选择本次任务的数据文件")
    return template, spec, await inspect_upload(spec.content, upload)


async def preview_input(
    session: AsyncSession,
    access: CategoryAccess,
    prompt_id: str,
    upload: tuple[str, bytes],
    *,
    version: str = VERSION_RELEASE,
) -> dict[str, Any]:
    """只检查不发起：不调用模型、不建任务、不动模板的测试样本。"""

    _, spec, summary = await _plan(session, access, prompt_id, upload, version=version, lock=False)
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
    template, spec, summary = await _plan(
        session, access, str(values.get("prompt_id") or ""), upload, version=version, lock=True
    )
    # 先取码表：码表服务不可用就不建任务，免得排进队列才发现没有码表。
    code = await _code(template, spec)
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
