from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from platform_common.errors import ApiError, ErrorCode, NotFoundError
from platform_common.responses import paginate
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import classified, require_audit_permission
from app.application import query as query_app
from app.core.database import get_db_session
from app.core.http_utils import success_json
from app.domain.enums import SecurityClass

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/events")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_audit_events(
    _auth: None = Depends(require_audit_permission("list")),
    session: AsyncSession = Depends(get_db_session),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    actor_id: str | None = None,
    actor_name: list[str] | None = Query(default=None),
    module_code: list[str] | None = Query(default=None),
    action_code: list[str] | None = Query(default=None),
    outcome: list[str] | None = Query(default=None),
) -> JSONResponse:
    items, total = await query_app.list_page(
        session,
        page=page,
        page_size=page_size,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        actor_id=actor_id,
        actor_name=actor_name,
        module_code=module_code,
        action_code=action_code,
        outcome=outcome,
    )
    page_data = paginate(
        [item.model_dump(mode="json") for item in items],
        total,
        page=page,
        page_size=page_size,
    )
    return success_json(page_data.model_dump())


@router.get("/events/options")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_filter_options(
    _auth: None = Depends(require_audit_permission("list")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    return success_json(await query_app.list_options(session))


@router.get("/events/options/search")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def search_filter_options(
    field: str = Query(..., min_length=1, max_length=64),
    q: str | None = Query(default=None, max_length=200),
    _auth: None = Depends(require_audit_permission("list")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """筛选项的服务端搜索。候选值过多的字段由前端按关键词调用。"""

    try:
        values = await query_app.search_options(session, field=field, keyword=q)
    except KeyError as exc:
        raise ApiError("未知的筛选字段", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
    return success_json({"items": values})


@router.get("/events/{event_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_audit_event(
    event_id: uuid.UUID,
    _auth: None = Depends(require_audit_permission("read")),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    item = await query_app.get_one(session, event_id)
    if item is None:
        raise NotFoundError("审计事件不存在")
    return success_json(item.model_dump(mode="json"))
