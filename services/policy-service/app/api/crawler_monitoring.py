from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.errors import ApiError, ErrorCode
from platform_common.http_utils import success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import classified, require_policy_permission
from app.application import crawler as service
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/policy/crawler-monitoring", tags=["policy-crawler-monitoring"])
RESOURCE = "policy.crawler_monitoring"


def _filters(
    province_name: str | None,
    city_name: str | None,
    site_name: str | None,
    site_code: str | None,
    tag: str | None,
    health_status: str | None,
    stale_days_min: int | None,
    abnormal_only: bool,
) -> dict[str, object]:
    return {
        "province_name": province_name,
        "city_name": city_name,
        "site_name": site_name,
        "site_code": site_code,
        "tag": tag,
        "health_status": health_status,
        "stale_days_min": stale_days_min,
        "abnormal_only": abnormal_only,
    }


@router.get("/overview")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_overview(
    trend_days: int = Query(default=30, ge=7, le=180),
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
):
    return success_json(await service.overview(session, trend_days=trend_days))


@router.get("/tasks")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_tasks(
    province_name: str | None = Query(default=None),
    city_name: str | None = Query(default=None),
    site_name: str | None = Query(default=None),
    site_code: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    health_status: str | None = Query(default=None),
    stale_days_min: int | None = Query(default=None, ge=0),
    abnormal_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
):
    return success_json(
        await service.list_tasks(
            session,
            filters=_filters(
                province_name, city_name, site_name, site_code, tag, health_status, stale_days_min, abnormal_only
            ),
            page=page,
            page_size=page_size,
        )
    )


@router.get("/tasks/options")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_filter_options(
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
):
    return success_json(await service.list_options(session))


@router.get("/tasks/options/search")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def search_filter_options(
    field: str = Query(..., min_length=1, max_length=64),
    q: str | None = Query(default=None, max_length=200),
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
):
    try:
        values = await service.search_options(session, field=field, keyword=q)
    except KeyError as exc:
        raise ApiError("未知的筛选字段", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
    return success_json({"items": values})


@router.get("/tasks/detail")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_task_detail(
    site_code: str = Query(default="", max_length=100),
    tag: str = Query(default="", max_length=255),
    days: int = Query(default=90, ge=7, le=180),
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_policy_permission(RESOURCE, "read")),
):
    """标签是层级路径、编码可能为空，都不适合放 path 参数，统一走 query。"""

    return success_json(await service.task_detail(session, site_code=site_code, tag=tag, days=days))


@router.get("/tasks/export")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def export_tasks(
    province_name: str | None = Query(default=None),
    city_name: str | None = Query(default=None),
    site_name: str | None = Query(default=None),
    site_code: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    health_status: str | None = Query(default=None),
    stale_days_min: int | None = Query(default=None, ge=0),
    abnormal_only: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "export")),
):
    payload = await service.export_tasks(
        session,
        actor,
        _filters(province_name, city_name, site_name, site_code, tag, health_status, stale_days_min, abnormal_only),
    )
    name = "爬虫异常清单.xlsx" if abnormal_only else "爬虫监测.xlsx"
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )
