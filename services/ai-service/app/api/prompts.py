from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from platform_common.actors import Actor
from platform_common.http_utils import read_named_upload, success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import FileKind, PromptBody, file_response
from app.api.security import CategoryAccess, SecurityClass, classified, get_category_access, require_ai_permission
from app.application import prompts as service
from app.application import releases
from app.application.asking import available_models
from app.core.config import get_settings
from app.core.database import get_db_session
from app.domain.code_tables import SYSTEM_CODE_TABLES

router = APIRouter(prefix="/api/v1/ai/prompts", tags=["ai-prompts"])
RESOURCE = "ai.prompts"
RELEASE_RESOURCE = "ai.releases"


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_prompts(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(
        {
            "items": await service.list_prompts(session, access),
            "models": await available_models(session),
            "categories": access.options(),
            "code_tables": [{"key": key, "name": name} for key, name in SYSTEM_CODE_TABLES.items()],
        }
    )


@router.post("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_prompt(
    body: PromptBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "create")),
) -> JSONResponse:
    return success_json(await service.create_prompt(session, actor, access, body.model_dump()), status_code=201)


@router.put("/{prompt_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_prompt(
    prompt_id: str,
    body: PromptBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "update")),
) -> JSONResponse:
    return success_json(await service.update_prompt(session, actor, access, prompt_id, body.model_dump()))


@router.delete("/{prompt_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def delete_prompt(
    prompt_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "delete")),
) -> JSONResponse:
    await service.delete_prompt(session, actor, access, prompt_id)
    return success_json(None)


@router.post("/{prompt_id}/files/{kind}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def upload_file(
    prompt_id: str,
    kind: FileKind,
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "update")),
) -> JSONResponse:
    # 鉴权通过后才解析 multipart，并且边读边按上限中止。
    content, filename = await read_named_upload(request, get_settings().upload_max_bytes, missing="请选择要上传的文件")
    return success_json(await service.upload_file(session, actor, access, prompt_id, kind, (filename, content)))


@router.delete("/{prompt_id}/files/{kind}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def delete_file(
    prompt_id: str,
    kind: FileKind,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "update")),
) -> JSONResponse:
    return success_json(await service.delete_file(session, actor, access, prompt_id, kind))


@router.get("/{prompt_id}/files/{kind}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def download_file(
    prompt_id: str,
    kind: FileKind,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "export")),
) -> Response:
    content, filename = await service.download_file(session, actor, access, prompt_id, kind)
    return file_response(content, filename)


@router.get("/{prompt_id}/releases")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_releases(
    prompt_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await releases.list_releases(session, access, prompt_id))


@router.post("/{prompt_id}/release")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def publish(
    prompt_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RELEASE_RESOURCE, "publish")),
) -> JSONResponse:
    """上线是管理员的事：业务人员能改模板，但不能让改动直接进定时任务。"""

    return success_json(await releases.publish(session, actor, access, prompt_id))


@router.post("/{prompt_id}/offline")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def take_offline(
    prompt_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    access: CategoryAccess = Depends(get_category_access),
    actor: Actor = Depends(require_ai_permission(RELEASE_RESOURCE, "publish")),
) -> JSONResponse:
    return success_json(await releases.take_offline(session, actor, access, prompt_id))
