"""模型配置页：查看、新增、编辑。不提供删除，模板和历史任务按模型 ID 引用，不用了就停用。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from platform_common.actors import Actor
from platform_common.http_utils import success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ModelBody
from app.api.security import SecurityClass, classified, require_ai_permission
from app.application import model_configs as service
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/ai/models", tags=["ai-models"])
RESOURCE = "ai.models"


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_models(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_ai_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.list_models(session))


@router.post("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_model(
    body: ModelBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "create")),
) -> JSONResponse:
    return success_json(await service.create_model(session, actor, body.model_dump()), status_code=201)


@router.put("/{model_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_model(
    model_id: str,
    body: ModelBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_ai_permission(RESOURCE, "update")),
) -> JSONResponse:
    return success_json(await service.update_model(session, actor, model_id, body.model_dump()))
