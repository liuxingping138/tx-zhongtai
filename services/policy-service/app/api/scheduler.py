from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.http_utils import success_json
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import classified, require_policy_permission
from app.application import scheduler as service
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/policy/scheduled-jobs", tags=["任务调度"])
RESOURCE = "system.scheduler"


class JobUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    daily_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    version: int = Field(ge=1)


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_jobs(
    session: AsyncSession = Depends(get_db_session), _: Actor = Depends(require_policy_permission(RESOURCE, "list"))
) -> JSONResponse:
    return success_json(jsonable_encoder(await service.list_jobs(session)))


@router.patch("/{code}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_job(
    code: str,
    payload: JobUpdate,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "update")),
) -> JSONResponse:
    await service.update_job(session, code, actor, **payload.model_dump())
    return success_json({"saved": True})


@router.post("/{code}/runs", status_code=202)
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def trigger_job(
    code: str,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "execute")),
) -> JSONResponse:
    return success_json(jsonable_encoder(await service.trigger_job(session, code, actor)), status_code=202)


@router.get("/{code}/runs")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def history(
    code: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(jsonable_encoder(await service.history(session, code, page, page_size)))
