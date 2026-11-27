"""智库专属 6 张码表的公开 REST 路由。每张码表按独立 IAM 资源码挂载权限依赖。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.errors import ApiError, ErrorCode
from platform_common.http_utils import (
    IMPORT_FILE_OPENAPI,
    content_disposition,
    import_result_response,
    read_import_upload,
    success_json,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ThinktankDictPatch, ThinktankDictWrite
from app.api.security import classified, require_codebook_permission
from app.application import thinktank_dicts as service
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.domain.thinktank_dicts import THINKTANK_DICT_SPECS, ThinktankDictSpec


def _build_router(spec: ThinktankDictSpec) -> APIRouter:
    sub = APIRouter(
        prefix=f"/api/v1/codebook/thinktank/{spec.slug}",
        tags=[f"codebook-thinktank-{spec.slug}"],
    )
    dict_type = spec.dict_type
    resource = spec.resource

    @sub.get("")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def list_items(
        keyword: list[str] | None = Query(default=None),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        session: AsyncSession = Depends(get_db_session, scope="function"),
        _: Actor = Depends(require_codebook_permission(resource, "list")),
    ) -> JSONResponse:
        return success_json(
            await service.list_dicts(session, dict_type, keyword=keyword, page=page, page_size=page_size)
        )

    @sub.get("/options")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def list_filter_options(
        session: AsyncSession = Depends(get_db_session, scope="function"),
        _: Actor = Depends(require_codebook_permission(resource, "list")),
    ) -> JSONResponse:
        return success_json(await service.list_dict_options(session, dict_type))

    @sub.get("/options/search")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def search_filter_options(
        field: str = Query(..., min_length=1, max_length=64),
        q: str | None = Query(default=None, max_length=200),
        session: AsyncSession = Depends(get_db_session, scope="function"),
        _: Actor = Depends(require_codebook_permission(resource, "list")),
    ) -> JSONResponse:
        try:
            values = await service.search_dict_options(session, dict_type, field=field, keyword=q)
        except KeyError as exc:
            raise ApiError("未知的筛选字段", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
        return success_json({"items": values})

    @sub.get("/export")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def export_items(
        keyword: list[str] | None = Query(default=None),
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_codebook_permission(resource, "export")),
    ) -> Response:
        payload = await service.export_dicts(session, actor, dict_type, {"keyword": keyword})
        return Response(
            content=payload,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": content_disposition(
                    "attachment", f"{spec.title}.xlsx", fallback=f"thinktank-{spec.slug}.xlsx"
                ),
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )

    @sub.post("/import", openapi_extra=IMPORT_FILE_OPENAPI)
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def import_items(
        request: Request,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_codebook_permission(resource, "import")),
        settings: Settings = Depends(get_settings),
    ) -> Response:
        content = await read_import_upload(request, settings.import_max_bytes)
        return import_result_response(
            await service.import_dicts(session, actor, dict_type, content),
            f"{spec.title}-跳过明细.xlsx",
        )

    @sub.post("")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def create_item(
        body: ThinktankDictWrite,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_codebook_permission(resource, "create")),
    ) -> JSONResponse:
        return success_json(
            await service.create_dict(session, actor, dict_type, body.model_dump()),
            status_code=201,
        )

    @sub.patch("/{item_id}")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def update_item(
        item_id: uuid.UUID,
        body: ThinktankDictPatch,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_codebook_permission(resource, "update")),
    ) -> JSONResponse:
        return success_json(
            await service.update_dict(session, actor, dict_type, item_id, body.model_dump(exclude_unset=True))
        )

    @sub.delete("/{item_id}")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def delete_item(
        item_id: uuid.UUID,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_codebook_permission(resource, "delete")),
    ) -> JSONResponse:
        return success_json(await service.delete_dict(session, actor, dict_type, item_id))

    return sub


router = APIRouter()
for _spec in THINKTANK_DICT_SPECS:
    router.include_router(_build_router(_spec))
