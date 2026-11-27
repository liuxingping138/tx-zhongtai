"""智库统计中心路由：全局统计大盘、单文档动态速览、Excel 统计简报导出。"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response
from platform_common.actors import Actor
from platform_common.http_utils import success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.security import SecurityClass, classified, require_thinktank_permission
from app.core.database import get_db_session
from app.statistics.application.export import export_statistics_excel
from app.statistics.application.statistics import get_document_detail, get_statistics_overview
from app.statistics.domain.specs import Granularity, LibraryKey, LibraryScope, RangePreset, StatisticsQuery

RESOURCE = "thinktank.statistics"
_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
router = APIRouter(prefix="/api/v1/thinktank/statistics", tags=["thinktank-statistics"])


def statistics_query(
    library: LibraryScope = Query(default="all"),
    granularity: Granularity = Query(default="week"),
    preset: RangePreset = Query(default="30d"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
) -> StatisticsQuery:
    return StatisticsQuery(
        library=library,
        granularity=granularity,
        preset=preset,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def statistics_overview(
    _actor: Annotated[Actor, Depends(require_thinktank_permission(RESOURCE, "list"))],
    session: Annotated[AsyncSession, Depends(get_db_session, scope="function")],
    query: Annotated[StatisticsQuery, Depends(statistics_query)],
) -> JSONResponse:
    data = await get_statistics_overview(session, query=query)
    return success_json(data)


@router.get("/documents/{library}/{file_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def document_peek(
    library: LibraryKey,
    file_id: uuid.UUID,
    _actor: Annotated[Actor, Depends(require_thinktank_permission(RESOURCE, "list"))],
    session: Annotated[AsyncSession, Depends(get_db_session, scope="function")],
) -> JSONResponse:
    data = await get_document_detail(session, library=library, file_id=file_id)
    return success_json(data)


@router.get("/export")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def statistics_export(
    actor: Annotated[Actor, Depends(require_thinktank_permission(RESOURCE, "export"))],
    session: Annotated[AsyncSession, Depends(get_db_session, scope="function")],
    query: Annotated[StatisticsQuery, Depends(statistics_query)],
) -> Response:
    payload = await export_statistics_excel(session, actor=actor, query=query)
    await session.commit()
    filename = f"智库统计简报_{query.library}_{query.preset}.xlsx"
    encoded = quote(filename)
    return Response(
        content=payload,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )
