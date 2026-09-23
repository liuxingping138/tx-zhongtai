from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.errors import ApiError, ErrorCode
from platform_common.http_utils import import_result_response, read_upload_within_limit, success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import SourceClearRequest, SourceWrite
from app.api.security import classified, require_policy_permission
from app.application import sources as service
from app.core.config import Settings, get_settings
from app.core.database import get_db_session

router = APIRouter(prefix="/api/v1/policy/sources", tags=["policy-sources"])
RESOURCE = "policy.sources"


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_items(
    site_name: list[str] | None = Query(default=None),
    province_name: list[str] | None = Query(default=None),
    city_name: list[str] | None = Query(default=None),
    tag: list[str] | None = Query(default=None),
    site_code: list[str] | None = Query(default=None),
    crawl_priority: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
):
    return success_json(
        await service.list_sources(
            session,
            site_name=site_name,
            province_name=province_name,
            city_name=city_name,
            tag=tag,
            site_code=site_code,
            crawl_priority=crawl_priority,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/options")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_filter_options(
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
):
    return success_json(await service.list_source_options(session))


@router.get("/options/search")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def search_filter_options(
    field: str = Query(..., min_length=1, max_length=64),
    q: str | None = Query(default=None, max_length=200),
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_policy_permission(RESOURCE, "list")),
):
    """筛选项的服务端搜索。候选值过多的字段由前端按关键词调用。"""

    try:
        values = await service.search_source_options(session, field=field, keyword=q)
    except KeyError as exc:
        raise ApiError("未知的筛选字段", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
    return success_json({"items": values})


@router.get("/export")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def export_items(
    site_name: list[str] | None = Query(default=None),
    province_name: list[str] | None = Query(default=None),
    city_name: list[str] | None = Query(default=None),
    tag: list[str] | None = Query(default=None),
    site_code: list[str] | None = Query(default=None),
    crawl_priority: list[str] | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "export")),
):
    # 导出复用列表的筛选条件，保证「所见即所导」。
    payload = await service.export_sources(
        session,
        actor,
        {
            "site_name": site_name,
            "province_name": province_name,
            "city_name": city_name,
            "tag": tag,
            "site_code": site_code,
            "crawl_priority": crawl_priority,
        },
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
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "purge")),
):
    if body.confirm != "清空":
        raise ApiError("请输入确认口令「清空」", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return success_json(await service.purge_sources(session, actor))


@router.post("/import")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def import_items(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "import")),
    settings: Settings = Depends(get_settings),
):
    content = await read_upload_within_limit(file, settings.import_max_bytes)
    return import_result_response(await service.import_sources(session, actor, content), "sources-import.xlsx")


@router.post("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def create_item(
    body: SourceWrite,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "create")),
):
    return success_json(
        await service.create_source(session, actor, body.model_dump(exclude={"version"})),
        status_code=201,
    )


@router.get("/{item_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    _: Actor = Depends(require_policy_permission(RESOURCE, "read")),
):
    return success_json(await service.get_source(session, item_id))


@router.patch("/{item_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_item(
    item_id: uuid.UUID,
    body: SourceWrite,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_policy_permission(RESOURCE, "update")),
):
    return success_json(await service.update_source(session, actor, item_id, body.model_dump()))
