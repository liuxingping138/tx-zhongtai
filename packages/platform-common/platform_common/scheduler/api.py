"""任务调度页的四个接口。各服务挂在自己的前缀下（如 /api/v1/policy/scheduled-jobs），资源统一是 system.scheduler：
查看档能看任务和执行记录，完整档才能改计划、手动执行。前端调度页把各服务的任务汇总到一张表。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.http_utils import success_json
from platform_common.scheduler.store import Scheduler
from platform_common.service_authz import classified

RESOURCE = "system.scheduler"


class JobUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    daily_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    version: int = Field(ge=1)


def build_scheduler_router(
    scheduler: Scheduler,
    *,
    prefix: str,
    require_permission: Callable[[str, str], Callable[..., Any]],
    get_db_session: Callable[..., Any],
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["任务调度"])

    @router.get("")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def list_jobs(
        session: AsyncSession = Depends(get_db_session, scope="function"),
        _: Actor = Depends(require_permission(RESOURCE, "list")),
    ) -> JSONResponse:
        return success_json(jsonable_encoder(await scheduler.list_jobs(session)))

    @router.patch("/{code}")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def update_job(
        code: str,
        payload: JobUpdate,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_permission(RESOURCE, "update")),
    ) -> JSONResponse:
        await scheduler.update_job(session, code, actor, **payload.model_dump())
        return success_json({"saved": True})

    @router.post("/{code}/runs", status_code=202)
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def trigger_job(
        code: str,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_permission(RESOURCE, "execute")),
    ) -> JSONResponse:
        return success_json(jsonable_encoder(await scheduler.trigger_job(session, code, actor)), status_code=202)

    @router.get("/{code}/runs")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def history(
        code: str,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        session: AsyncSession = Depends(get_db_session, scope="function"),
        _: Actor = Depends(require_permission(RESOURCE, "list")),
    ) -> JSONResponse:
        return success_json(jsonable_encoder(await scheduler.history(session, code, page, page_size)))

    return router
