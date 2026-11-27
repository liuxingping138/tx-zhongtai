"""报告库与方案库统一路由工厂：与资料库完整功能对齐。"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from platform_common.actors import Actor
from platform_common.enums import SecurityClass
from platform_common.errors import ApiError, ErrorCode
from platform_common.filters import Filters
from platform_common.http_utils import (
    IMPORT_FILE_OPENAPI,
    import_result_response,
    read_import_upload,
    success_json,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.content_response import content_disposition, inline_content_response, streamed
from app.common.security import LibraryAccess, classified, get_library_access, require_thinktank_permission
from app.common.upload_utils import read_upload_with_fields
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.library.api.schemas import ProposalPatch, ReportPatch, proposal_filters, report_filters
from app.library.application import export_import
from app.library.application import library_read as read_service
from app.library.application import library_write as write_service
from app.library.domain.specs import PROPOSAL_SPEC, REPORT_SPEC, LibrarySpec


def _register_collection_routes(router: APIRouter, spec: LibrarySpec, filters_dep: Callable[..., Filters]) -> None:
    resource = spec.resource

    @router.get("")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def list_items(
        filters: Filters = Depends(filters_dep),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_thinktank_permission(resource, "list")),
        access: LibraryAccess = Depends(get_library_access),
    ) -> JSONResponse:
        return success_json(
            await read_service.list_library(
                session, spec, actor=actor, access=access, filters=filters, pagination=(page, page_size)
            )
        )

    @router.get("/options")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def list_filter_options(
        session: AsyncSession = Depends(get_db_session, scope="function"),
        _: Actor = Depends(require_thinktank_permission(resource, "list")),
    ) -> JSONResponse:
        return success_json(await read_service.get_options(session, spec))

    @router.get("/options/search")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def search_filter_options(
        field: str = Query(..., min_length=1, max_length=64),
        q: str | None = Query(default=None, max_length=200),
        session: AsyncSession = Depends(get_db_session, scope="function"),
        _: Actor = Depends(require_thinktank_permission(resource, "list")),
    ) -> JSONResponse:
        try:
            values = await read_service.search_options(session, spec, field=field, keyword=q)
        except KeyError as exc:
            raise ApiError("未知的筛选字段", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
        return success_json({"items": values})

    @router.get("/export")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def export_items(
        filters: Filters = Depends(filters_dep),
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_thinktank_permission(resource, "export")),
    ) -> Response:
        payload = await export_import.export_filtered_excel(session, spec, actor=actor, filters=filters)
        return Response(
            content=payload,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": content_disposition(
                    "attachment", spec.export_filename, fallback=f"{spec.fallback_stem}.xlsx"
                )
            },
        )

    @router.get("/export-undefined")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def export_undefined_items(
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_thinktank_permission(resource, "export_undefined")),
    ) -> Response:
        payload = await export_import.export_undefined_excel(session, spec, actor=actor)
        return Response(
            content=payload,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": content_disposition(
                    "attachment", spec.undefined_filename, fallback=f"{spec.fallback_stem}-undefined.xlsx"
                )
            },
        )

    @router.post("/upload", openapi_extra=IMPORT_FILE_OPENAPI)
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def upload_file(
        request: Request,
        background_tasks: BackgroundTasks,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_thinktank_permission(resource, "create")),
        access: LibraryAccess = Depends(get_library_access),
        settings: Settings = Depends(get_settings),
    ) -> JSONResponse:
        content, filename, metadata = await read_upload_with_fields(
            request, settings.upload_max_bytes, missing=spec.missing_upload_msg
        )
        created = await write_service.upload_file(
            session,
            spec,
            actor=actor,
            access=access,
            payload=write_service.UploadPayload(filename=filename, content=content, metadata=metadata),
        )
        read_service.schedule_upload_warmup(background_tasks, settings, spec.slug, created["id"])
        return success_json(created, status_code=201)

    @router.post("/upload-tags", openapi_extra=IMPORT_FILE_OPENAPI)
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def upload_tags(
        request: Request,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_thinktank_permission(resource, "upload_tags")),
        settings: Settings = Depends(get_settings),
    ) -> Response:
        content = await read_import_upload(request, settings.import_max_bytes)
        result = await export_import.upload_tags(session, spec, actor=actor, content=content)
        return import_result_response(result, spec.skip_filename)


def _register_item_read_routes(router: APIRouter, spec: LibrarySpec) -> None:
    resource = spec.resource

    @router.get("/{file_id}")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def get_item(
        file_id: uuid.UUID,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_thinktank_permission(resource, "read")),
        access: LibraryAccess = Depends(get_library_access),
    ) -> JSONResponse:
        return success_json(await read_service.get_detail(session, spec, actor=actor, access=access, file_id=file_id))

    @router.get("/{file_id}/preview")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def preview_item(
        file_id: uuid.UUID,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_thinktank_permission(resource, "preview")),
        access: LibraryAccess = Depends(get_library_access),
    ) -> JSONResponse:
        return success_json(await read_service.preview_item(session, spec, actor=actor, access=access, file_id=file_id))

    @router.get("/{file_id}/content")
    @router.head("/{file_id}/content")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def get_item_content(
        file_id: uuid.UUID,
        request: Request,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_thinktank_permission(resource, "preview")),
    ) -> Response:
        res = await read_service.stream_file_content(
            session,
            spec,
            actor=actor,
            file_id=file_id,
            for_download=False,
            if_none_match=request.headers.get("if-none-match"),
        )
        return inline_content_response(
            res,
            head=request.method == "HEAD",
            range_header=request.headers.get("range"),
            if_range=request.headers.get("if-range"),
            fallback=spec.fallback_stem,
        )

    @router.get("/{file_id}/download")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def download_item(
        file_id: uuid.UUID,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_thinktank_permission(resource, "download")),
    ) -> StreamingResponse:
        res = await read_service.stream_file_content(session, spec, actor=actor, file_id=file_id, for_download=True)
        headers = {
            "Content-Disposition": content_disposition("attachment", res.filename, fallback=spec.fallback_stem),
            "Access-Control-Expose-Headers": "Content-Disposition",
        }
        if res.content_length is not None:
            headers["Content-Length"] = str(res.content_length)
        return streamed(res, headers)

    @router.get("/{file_id}/logs")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def list_item_logs(
        file_id: uuid.UUID,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=10, ge=1, le=100),
        session: AsyncSession = Depends(get_db_session, scope="function"),
        _: Actor = Depends(require_thinktank_permission(resource, "read")),
    ) -> JSONResponse:
        return success_json(
            await read_service.list_logs(session, spec, file_id=file_id, page=page, page_size=page_size)
        )


def _register_item_write_routes(router: APIRouter, spec: LibrarySpec, patch_model: type[BaseModel]) -> None:
    resource = spec.resource

    @router.post("/{file_id}/favorite")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def favorite_item(
        file_id: uuid.UUID,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_thinktank_permission(resource, "favorite")),
    ) -> JSONResponse:
        return success_json(
            await read_service.toggle_favorite(session, spec, actor=actor, file_id=file_id, favorite=True)
        )

    @router.delete("/{file_id}/favorite")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def unfavorite_item(
        file_id: uuid.UUID,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_thinktank_permission(resource, "favorite")),
    ) -> JSONResponse:
        return success_json(
            await read_service.toggle_favorite(session, spec, actor=actor, file_id=file_id, favorite=False)
        )

    async def update_item(
        file_id: uuid.UUID,
        body: Any,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_thinktank_permission(resource, "update")),
        access: LibraryAccess = Depends(get_library_access),
    ) -> JSONResponse:
        return success_json(
            await write_service.update_metadata(
                session, spec, actor=actor, access=access, file_id=file_id, data=body.model_dump(exclude_unset=True)
            )
        )

    update_item.__annotations__["body"] = patch_model
    router.patch("/{file_id}")(classified(SecurityClass.RESOURCE_AUTHORIZED)(update_item))

    @router.delete("/{file_id}")
    @classified(SecurityClass.RESOURCE_AUTHORIZED)
    async def delete_item(
        file_id: uuid.UUID,
        session: AsyncSession = Depends(get_db_session, scope="function"),
        actor: Actor = Depends(require_thinktank_permission(resource, "delete")),
    ) -> JSONResponse:
        return success_json(await write_service.delete_file(session, spec, actor=actor, file_id=file_id))


def build_library_router(
    spec: LibrarySpec,
    *,
    filters_dep: Callable[..., Filters],
    patch_model: type[BaseModel],
) -> APIRouter:
    router = APIRouter(prefix=f"/api/v1/thinktank/{spec.slug}", tags=[f"thinktank-{spec.slug}"])
    _register_collection_routes(router, spec, filters_dep)
    _register_item_read_routes(router, spec)
    _register_item_write_routes(router, spec, patch_model)
    return router


reports_router = build_library_router(REPORT_SPEC, filters_dep=report_filters, patch_model=ReportPatch)
proposals_router = build_library_router(PROPOSAL_SPEC, filters_dep=proposal_filters, patch_model=ProposalPatch)
