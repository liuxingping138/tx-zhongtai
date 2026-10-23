"""爬虫配置统计：领导看的按周、按省统计和 Excel 下载。手动同步的入口在调度的 api（app.scheduler.api.config_sync）。"""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.http_utils import success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.security import classified, require_policy_permission
from app.core.database import get_db_session
from app.crawlconfig.application import report as service

router = APIRouter(prefix="/api/v1/policy/crawler-config", tags=["policy-crawler-config"])
RESOURCE = "policy.crawler_config"
WEEK_QUERY = Query(default=None, description="所选周内任意一天，默认本周（北京时间）")


@router.get("/report")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_report(
    week: date | None = WEEK_QUERY,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(jsonable_encoder(await service.build_report(session, week)))


@router.get("/report/export")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def export_report(
    week: date | None = WEEK_QUERY,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "export")),
) -> Response:
    content, filename = await service.export_report(session, actor, week)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )
