from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.errors import ApiError, ErrorCode
from platform_common.filters import Filters
from platform_common.http_utils import success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.security import classified, require_policy_permission
from app.core.database import get_db_session
from app.crawler.application import crawler_sites as service
from app.crawler.application import crawler_stats as stats
from app.crawler.application import crawler_status as status_history

router = APIRouter(prefix="/api/v1/policy/crawler-monitoring", tags=["policy-crawler-monitoring"])
RESOURCE = "policy.crawler_monitoring"

SiteStatus = Literal["normal", "watch", "stale"]


def site_filters(
    province_name: list[str] | None = Query(default=None),
    city_name: list[str] | None = Query(default=None),
    site_name: list[str] | None = Query(default=None),
    status: list[SiteStatus] | None = Query(default=None),
) -> Filters:
    return {"province_name": province_name, "city_name": city_name, "site_name": site_name, "status": status}


def _check_days(days: int) -> None:
    # 不用 Literal[30, 90, 365]：Pydantic 对 Literal 不做类型转换，查询串里的 "90" 会被当成非法值。
    if days not in stats.TREND_DAYS:
        raise ApiError("趋势范围只支持 7、30、90、365 天", code=ErrorCode.VALIDATION_ERROR, http_status=422)


@router.get("/overview")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_overview(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.overview(session))


@router.get("/trend")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_trend(
    days: int = Query(default=90),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    _check_days(days)
    return success_json(await stats.trend(session, days))


@router.get("/site-trend")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_site_trend(
    site_name: str = Query(..., min_length=1, max_length=255),
    province_name: str = Query(default="", max_length=64),
    city_name: str = Query(default="", max_length=64),
    days: int = Query(default=90),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    """按「网站名称 + 省份 + 地市」原始值查，不用快照 id：快照每次同步重建，id 会变。"""
    _check_days(days)
    return success_json(
        await status_history.site_trend(
            session, site_name=site_name, province_name=province_name, city_name=city_name, days=days
        )
    )


@router.get("/sites")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_sites(
    filters: Filters = Depends(site_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.list_sites(session, filters=filters, page=page, page_size=page_size))


@router.get("/sites/options")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_filter_options(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.list_options(session))


@router.get("/sites/options/search")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def search_filter_options(
    field: str = Query(..., min_length=1, max_length=64),
    q: str | None = Query(default=None, max_length=200),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    try:
        values = await service.search_filter_options(session, field=field, keyword=q)
    except KeyError as exc:
        raise ApiError("未知的筛选字段", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
    return success_json({"items": values})


@router.get("/sites/export")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def export_sites(
    filters: Filters = Depends(site_filters),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "export")),
) -> Response:
    payload = await service.export_sites(session, actor, filters)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote('爬虫监测.xlsx')}"},
    )
