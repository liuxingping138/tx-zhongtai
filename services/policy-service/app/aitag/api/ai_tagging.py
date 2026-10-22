"""政策 AI 打标的设置和执行记录。挂在任务调度资源下：查看看设置和记录，完整档才能改设置。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.http_utils import success_json
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.aitag.application import settings as service
from app.common.security import classified, require_policy_permission
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/policy/ai-tagging", tags=["政策AI打标"])
RESOURCE = "system.scheduler"


class ConfigBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type_prompt_id: str = Field(default="", max_length=32)
    interpret_prompt_id: str = Field(default="", max_length=32)
    opportunity_prompt_id: str = Field(default="", max_length=32)
    batch_size: int
    content_max_chars: int
    daily_cost_limit: str = Field(pattern=r"^\d{1,8}(\.\d{1,2})?$")
    cursor_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    version: int = Field(ge=1)


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def overview(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.overview(session))


@router.put("/config")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_config(
    body: ConfigBody,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "update")),
) -> JSONResponse:
    return success_json(await service.update(session, actor, body.model_dump()))


@router.get("/runs")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.runs(session, page, page_size))
