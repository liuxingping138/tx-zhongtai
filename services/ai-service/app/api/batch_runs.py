from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from platform_common.actors import Actor
from platform_common.filters import Filters
from platform_common.http_utils import read_named_upload, success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    BatchRowsPreviewBody,
    BatchRowsStartBody,
    RunFileKind,
    file_response,
    path_response,
)
from app.api.security import CategoryAccess, SecurityClass, classified, get_category_access, require_ai_permission
from app.application import batch_run_all, batch_start, prompts
from app.application import batch_runs as service
from app.application.asking import available_models
from app.core.config import get_settings
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/ai/batch-runs", tags=["ai-batch-runs"])
RESOURCE = "ai.batch_runs"
_MISSING_FILE = "请选择本次任务的数据文件"


RunMode = Literal["test", "all"]
RunSource = Literal["manual", "pipeline"]
RunVersion = Literal["release", "draft"]


def run_filters(
    prompt_title: list[str] | None = Query(default=None),
    prompt_category: list[str] | None = Query(default=None),
    created_by_name: list[str] | None = Query(default=None),
    run_mode: list[RunMode] | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    source: list[RunSource] | None = Query(default=None),
) -> Filters:
    return {
        "prompt_title": prompt_title,
        "prompt_category": prompt_category,
        "created_by_name": created_by_name,
        "run_mode": run_mode,
        "status": status,
        "source": source,
    }


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_runs(
    filters: Filters = Depends(run_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=15, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.list_runs(session, access, page=page, page_size=page_size, filters=filters))


@router.get("/filter-options")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def filter_options(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.filter_options(session, access))


@router.get("/options")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def options(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    """新建任务选模板用：只有批量权限、没有模板权限的人也要能选上线的模板运行。"""

    return success_json(
        {
            "templates": await prompts.list_prompts(session, access),
            "models": await available_models(session),
            "categories": access.options(),
        }
    )


@router.post("/input-preview")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def preview_input(
    request: Request,
    prompt_id: str = Query(max_length=32),
    version: RunVersion = Query(default="release", description="跑上线版本还是已保存的草稿"),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission(RESOURCE, "run")),
) -> JSONResponse:
    """选好文件先检查：不调用模型、不建任务。文件在权限依赖通过之后才读，边读边限流。"""

    content, filename = await read_named_upload(request, get_settings().upload_max_bytes, missing=_MISSING_FILE)
    return success_json(
        await batch_start.preview_input(session, access, prompt_id, (filename, content), version=version)
    )


@router.get("/input-template")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def input_template(
    prompt_id: str = Query(max_length=32),
    version: RunVersion = Query(default="release", description="跑上线版本还是已保存的草稿"),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission(RESOURCE, "run")),
) -> Response:
    """要跑任务的人才需要：和发起同一个权限。必须在 /{run_id} 之前声明，否则会被当成任务 ID。"""

    content, filename = await batch_start.input_template(session, access, prompt_id, version=version)
    return file_response(content, filename)


@router.post("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def start_run(
    request: Request,
    prompt_id: str = Query(max_length=32),
    thinking: bool = Query(default=False),
    limit: int = Query(default=0, ge=0, le=100_000),
    version: RunVersion = Query(default="release", description="跑上线版本还是已保存的草稿"),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "run")),
) -> JSONResponse:
    """带文件的 multipart，其余参数在 query 里。0 条表示跑全部。"""

    content, filename = await read_named_upload(request, get_settings().upload_max_bytes, missing=_MISSING_FILE)
    values = {"prompt_id": prompt_id, "thinking": thinking, "limit": limit, "version": version}
    return success_json(
        await batch_start.start_run(session, actor, access, values, upload=(filename, content)), status_code=201
    )


@router.post("/from-rows/preview")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def preview_rows(
    body: BatchRowsPreviewBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission(RESOURCE, "run")),
) -> JSONResponse:
    """从政策库取数后预检：不调用模型、不建任务。"""

    return success_json(
        await batch_start.preview_rows(
            session,
            access,
            body.prompt_id,
            {"file_name": body.file_name, "headers": body.headers, "rows": body.rows},
            version=body.version,
        )
    )


@router.post("/from-rows")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def start_run_from_rows(
    body: BatchRowsStartBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "run")),
) -> JSONResponse:
    """从政策库取数直接发起离线批量验证任务。"""

    values = {
        "prompt_id": body.prompt_id,
        "thinking": body.thinking,
        "limit": body.limit,
        "version": body.version,
    }
    data = {"file_name": body.file_name, "headers": body.headers, "rows": body.rows}
    return success_json(await batch_start.start_run_from_rows(session, actor, access, values, data), status_code=201)


@router.get("/{run_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.get_run(session, access, run_id))


@router.get("/{run_id}/rows")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def run_rows(
    run_id: str,
    failed_only: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.run_rows(session, access, run_id, failed_only=failed_only))


@router.post("/{run_id}/retry")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def retry_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "run")),
) -> JSONResponse:
    return success_json(await service.retry_run(session, actor, access, run_id))


@router.post("/{run_id}/run-all")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def run_all(
    run_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "run")),
) -> JSONResponse:
    """只跑了前几行的任务，用同一份数据和同一版提示词跑全部；前面答好的行沿用。"""

    return success_json(await batch_run_all.run_all(session, actor, access, run_id), status_code=201)


@router.post("/{run_id}/stop")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def stop_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "stop")),
) -> JSONResponse:
    return success_json(await service.stop_run(session, actor, access, run_id))


@router.delete("/{run_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def delete_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "delete")),
) -> JSONResponse:
    await service.delete_run(session, actor, access, run_id)
    return success_json(None)


@router.get("/{run_id}/files/{kind}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def download(
    run_id: str,
    kind: RunFileKind,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "export")),
) -> Response:
    path, filename = await service.download(session, actor, access, run_id, kind)
    return path_response(path, filename)
