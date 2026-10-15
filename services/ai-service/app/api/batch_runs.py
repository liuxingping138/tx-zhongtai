from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response
from platform_common.actors import Actor
from platform_common.filters import Filters
from platform_common.http_utils import success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import RunBody, RunFileKind, file_response
from app.api.security import SecurityClass, classified, require_ai_permission
from app.application import batch_runs as service
from app.application import prompts
from app.application.asking import available_models
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/ai/batch-runs", tags=["ai-batch-runs"])
RESOURCE = "ai.batch_runs"


RunMode = Literal["test", "all"]


def run_filters(
    prompt_title: list[str] | None = Query(default=None),
    created_by_name: list[str] | None = Query(default=None),
    run_mode: list[RunMode] | None = Query(default=None),
    status: list[str] | None = Query(default=None),
) -> Filters:
    return {"prompt_title": prompt_title, "created_by_name": created_by_name, "run_mode": run_mode, "status": status}


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_runs(
    filters: Filters = Depends(run_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=15, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.list_runs(session, page=page, page_size=page_size, filters=filters))


@router.get("/filter-options")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def filter_options(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.filter_options(session))


@router.get("/options")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def options(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    """批量页选模板用：只有批量权限、没有提问配置权限的人也要能选模板运行。"""

    return success_json({"templates": await prompts.list_prompts(session), "models": available_models()})


@router.post("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def start_run(
    body: RunBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "run")),
) -> JSONResponse:
    return success_json(await service.start_run(session, actor, body.model_dump()), status_code=201)


@router.get("/{run_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.get_run(session, run_id))


@router.post("/{run_id}/retry")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def retry_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "run")),
) -> JSONResponse:
    return success_json(await service.retry_run(session, actor, run_id))


@router.post("/{run_id}/stop")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def stop_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "stop")),
) -> JSONResponse:
    return success_json(await service.stop_run(session, actor, run_id))


@router.delete("/{run_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def delete_run(
    run_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "delete")),
) -> JSONResponse:
    await service.delete_run(session, actor, run_id)
    return success_json(None)


@router.get("/{run_id}/files/{kind}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def download(
    run_id: str,
    kind: RunFileKind,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "export")),
) -> Response:
    content, filename = await service.download(session, actor, run_id, kind)
    return file_response(content, filename)
