"""招中标只读路由；每个资源分别校验 IAM 权限。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from platform_common.request_context import get_request_id
from platform_common.responses import ApiResponse, ok

from app.api.security import SecurityClass, classified, require_tender_permission
from app.application import counts, records, statistics
from app.core.source import Row
from app.domain.fields import Kind, Status
from app.domain.queries import ListQuery, StatsQuery

router = APIRouter(prefix="/api/v1/tender", tags=["招中标"])


@router.get("/statistics/totals", dependencies=[Depends(require_tender_permission("tender.statistics", "list"))])
@classified(SecurityClass.RESOURCE_AUTHORIZED)
def totals() -> ApiResponse[Row]:
    return ok(counts.get_totals(), request_id=get_request_id())


@router.get("/statistics", dependencies=[Depends(require_tender_permission("tender.statistics", "list"))])
@classified(SecurityClass.RESOURCE_AUTHORIZED)
def report(query: Annotated[StatsQuery, Query()]) -> ApiResponse[Row]:
    return ok(statistics.get_statistics(query), request_id=get_request_id())


def record_router(kind: Kind) -> APIRouter:
    child = APIRouter(prefix=f"/{kind}")
    resource = f"tender.{kind}"

    @child.get("", dependencies=[Depends(require_tender_permission(resource, "list"))])
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    def listing(query: Annotated[ListQuery, Query()]) -> ApiResponse[Row]:
        return ok(records.list_records(kind, query), request_id=get_request_id())

    @child.get("/count", dependencies=[Depends(require_tender_permission(resource, "list"))])
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    def count(query: Annotated[ListQuery, Query()]) -> ApiResponse[Row]:
        return ok(counts.get_count(kind, query), request_id=get_request_id())

    @child.get("/export", dependencies=[Depends(require_tender_permission(resource, "export"))])
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def export_items(query: Annotated[ListQuery, Query()]) -> Response:
        payload = await records.export_records(kind, query)
        return Response(
            content=payload,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="tender-{kind}.xlsx"'},
        )

    @child.get("/{record_id}", dependencies=[Depends(require_tender_permission(resource, "read"))])
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    def detail(
        record_id: Annotated[int, Path(gt=0)], project_status: Annotated[Status, Query()] = "0"
    ) -> ApiResponse[Row]:
        return ok(records.get_record(kind, project_status, record_id), request_id=get_request_id())

    @child.get("/{record_id}/content", dependencies=[Depends(require_tender_permission(resource, "read"))])
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    def content(
        record_id: Annotated[int, Path(gt=0)], project_status: Annotated[Status, Query()] = "0"
    ) -> ApiResponse[Row]:
        return ok(records.get_content(kind, project_status, record_id), request_id=get_request_id())

    return child


router.include_router(record_router("purchaser"))
router.include_router(record_router("winbid"))
