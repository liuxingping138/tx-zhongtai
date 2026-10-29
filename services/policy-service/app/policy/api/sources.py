from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.errors import ApiError, ErrorCode
from platform_common.filters import Filters
from platform_common.http_utils import IMPORT_FILE_OPENAPI, import_result_response, read_import_upload, success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.security import classified, require_policy_permission
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.policy.api.schemas import SourceClearRequest, SourcePatch, SourceStatusRequest, SourceWrite
from app.policy.application import source_import, source_status
from app.policy.application import sources as service

router = APIRouter(prefix="/api/v1/policy/sources", tags=["policy-sources"])
RESOURCE = "policy.sources"
# 日期筛选允许空串：前端没选日期时会带上空参数。
DATE_PATTERN = r"^(\d{4}-\d{2}-\d{2})?$"


def source_filters(
    site_name: list[str] | None = Query(default=None),
    province_name: list[str] | None = Query(default=None),
    city_name: list[str] | None = Query(default=None),
    tag: list[str] | None = Query(default=None),
    site_code: list[str] | None = Query(default=None),
    crawl_priority: list[str] | None = Query(default=None),
    site_type: list[str] | None = Query(default=None),
    crawler_status: list[str] | None = Query(default=None),
    online_date_from: str | None = Query(default=None, pattern=DATE_PATTERN, description="上线时间起，含当天"),
    online_date_to: str | None = Query(default=None, pattern=DATE_PATTERN, description="上线时间止，含当天"),
) -> Filters:
    return {
        "site_name": site_name,
        "province_name": province_name,
        "city_name": city_name,
        "tag": tag,
        "site_code": site_code,
        "crawl_priority": crawl_priority,
        "site_type": site_type,
        "crawler_status": crawler_status,
        "online_date_from": online_date_from,
        "online_date_to": online_date_to,
    }


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_items(
    filters: Filters = Depends(source_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(
        await service.list_sources(
            session,
            filters,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/options")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_filter_options(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    return success_json(await service.list_source_options(session))


@router.get("/options/search")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def search_filter_options(
    field: str = Query(..., min_length=1, max_length=64),
    q: str | None = Query(default=None, max_length=200),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
) -> JSONResponse:
    """筛选项的服务端搜索。候选值过多的字段由前端按关键词调用。"""

    try:
        values = await service.search_source_options(session, field=field, keyword=q)
    except KeyError as exc:
        raise ApiError("未知的筛选字段", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
    return success_json({"items": values})


@router.get("/export")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def export_items(
    filters: Filters = Depends(source_filters),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "export")),
) -> Response:
    # 导出复用列表的筛选条件，保证「所见即所导」。
    payload = await service.export_sources(
        session,
        actor,
        filters,
    )
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="policy-sources.xlsx"'},
    )


@router.post("/clear")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def clear_items(
    body: SourceClearRequest,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "purge")),
) -> JSONResponse:
    if body.confirm != "清空":
        raise ApiError("请输入确认口令「清空」", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return success_json(await service.purge_sources(session, actor))


@router.post("/crawler-status")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def set_crawler_status(
    body: SourceStatusRequest,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "update")),
) -> JSONResponse:
    """勾选多条批量改爬虫状态，改成「已爬」的上线时间记为当天。"""

    return success_json(await source_status.set_crawler_status(session, actor, body.ids, body.crawler_status))


@router.post("/import", openapi_extra=IMPORT_FILE_OPENAPI)
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def import_items(
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "import")),
    settings: Settings = Depends(get_settings),
) -> Response:
    content = await read_import_upload(request, settings.import_max_bytes)
    return import_result_response(await source_import.import_sources(session, actor, content), "sources-import.xlsx")


@router.post("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_item(
    body: SourceWrite,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "create")),
) -> JSONResponse:
    return success_json(
        await service.create_source(session, actor, body.model_dump(exclude={"version"})),
        status_code=201,
    )


@router.get("/{item_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_policy_permission(RESOURCE, "read")),
) -> JSONResponse:
    return success_json(await service.get_source(session, item_id))


@router.patch("/{item_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_item(
    item_id: uuid.UUID,
    body: SourcePatch,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "update")),
) -> JSONResponse:
    return success_json(await service.update_source(session, actor, item_id, body.model_dump(exclude_unset=True)))
