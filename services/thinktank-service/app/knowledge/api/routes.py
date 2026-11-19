"""知识库路由与鉴权依赖。"""

from __future__ import annotations

import re
import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from platform_common.actors import Actor
from platform_common.authz import AuthzClient
from platform_common.enums import SecurityClass
from platform_common.errors import ApiError, ErrorCode
from platform_common.filters import Filters
from platform_common.http_utils import (
    IMPORT_FILE_OPENAPI,
    import_result_response,
    read_import_upload,
    read_named_upload,
    success_json,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.security import classified, fetch_scope_levels, get_authz_client, require_thinktank_permission
from app.core.config import Settings, get_settings
from app.core.database import get_db_session
from app.knowledge.api.schemas import KnowledgePatch
from app.knowledge.application import export_import
from app.knowledge.application import knowledge as service
from app.knowledge.application import knowledge_write as write_service
from app.knowledge.domain.scopes import ALL_SCOPE_RESOURCES, KnowledgeAccess

router = APIRouter(prefix="/api/v1/thinktank/knowledge", tags=["thinktank-knowledge"])
RESOURCE = "thinktank.knowledge"


async def get_knowledge_access(
    request: Request,
    client: Annotated[AuthzClient, Depends(get_authz_client)],
) -> KnowledgeAccess:
    """加载当前用户在各文件类型、行业类型上的授权档位，并按子库菜单档位封顶。"""

    levels = await fetch_scope_levels(request, client, ALL_SCOPE_RESOURCES, "list")
    module_level = getattr(request.state, "authz_level", None)
    return KnowledgeAccess.from_levels(levels, module_level=module_level)


def knowledge_filters(
    file_name: list[str] | None = Query(default=None),
    file_type: list[str] | None = Query(default=None),
    operator_type: list[str] | None = Query(default=None),
    product_type: list[str] | None = Query(default=None),
    product_sub_type: list[str] | None = Query(default=None),
    industry_type: list[str] | None = Query(default=None),
    prov_name: list[str] | None = Query(default=None),
    app_scenario: list[str] | None = Query(default=None),
    depart_affiliation: list[str] | None = Query(default=None),
    market_category: list[str] | None = Query(default=None),
    data_time: list[str] | None = Query(default=None),
    tag_status: list[str] | None = Query(default=None),
    favorite_only: list[str] | None = Query(default=None),
) -> Filters:
    return {
        "file_name": file_name,
        "file_type": file_type,
        "operator_type": operator_type,
        "product_type": product_type,
        "product_sub_type": product_sub_type,
        "industry_type": industry_type,
        "prov_name": prov_name,
        "app_scenario": app_scenario,
        "depart_affiliation": depart_affiliation,
        "market_category": market_category,
        "data_time": data_time,
        "tag_status": tag_status,
        "favorite_only": favorite_only,
    }


_UNSAFE_HEADER_CHARS = re.compile(r'[\x00-\x1f\x7f"\\]')


def _content_disposition(disposition: str, filename: str) -> str:
    safe_name = _UNSAFE_HEADER_CHARS.sub("_", filename).strip() or "knowledge-file"
    ascii_fallback = safe_name.encode("ascii", "ignore").decode("ascii").strip() or "knowledge-file"
    encoded = quote(safe_name)
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_items(
    filters: Filters = Depends(knowledge_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "list")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
) -> JSONResponse:
    return success_json(
        await service.list_knowledge(
            session, actor=actor, access=access, filters=filters, page=page, page_size=page_size
        )
    )


@router.get("/access")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_access_scope(
    _: Actor = Depends(require_thinktank_permission(RESOURCE, "list")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
) -> JSONResponse:
    return success_json(access.to_summary())


@router.get("/options")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_filter_options(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_thinktank_permission(RESOURCE, "list")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
) -> JSONResponse:
    return success_json(await service.get_options(session, access=access))


@router.get("/options/search")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def search_filter_options(
    field: str = Query(..., min_length=1, max_length=64),
    q: str | None = Query(default=None, max_length=200),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: Actor = Depends(require_thinktank_permission(RESOURCE, "list")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
) -> JSONResponse:
    try:
        values = await service.search_options(session, field=field, keyword=q, access=access)
    except KeyError as exc:
        raise ApiError("未知的筛选字段", code=ErrorCode.VALIDATION_ERROR, http_status=422) from exc
    return success_json({"items": values})


@router.get("/export")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def export_items(
    filters: Filters = Depends(knowledge_filters),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "export")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
) -> Response:
    payload = await export_import.export_filtered_excel(session, actor=actor, access=access, filters=filters)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition("attachment", "知识库资料.xlsx")},
    )


@router.get("/export-undefined")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def export_undefined_items(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "export_undefined")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
) -> Response:
    payload = await export_import.export_undefined_excel(session, actor=actor, access=access)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition("attachment", "未定义标签数据.xlsx")},
    )


@router.post("/upload", openapi_extra=IMPORT_FILE_OPENAPI)
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def upload_file(
    request: Request,
    file_type: str = Query(default=""),
    operator_type: str = Query(default=""),
    depart_affiliation: str = Query(default=""),
    industry_type: str = Query(default=""),
    app_scenario: str = Query(default=""),
    market_category: str = Query(default=""),
    product_type: str = Query(default=""),
    product_sub_type: str = Query(default=""),
    prov_name: str = Query(default=""),
    data_time: str = Query(default=""),
    remark: str = Query(default=""),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "create")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    content, filename = await read_named_upload(request, settings.upload_max_bytes, missing="请上传知识文件")
    metadata = {
        "file_type": file_type,
        "operator_type": operator_type,
        "depart_affiliation": depart_affiliation,
        "industry_type": industry_type,
        "app_scenario": app_scenario,
        "market_category": market_category,
        "product_type": product_type,
        "product_sub_type": product_sub_type,
        "prov_name": prov_name,
        "data_time": data_time,
        "remark": remark,
    }
    created = await write_service.upload_knowledge_file(
        session, actor=actor, access=access, filename=filename, content=content, metadata=metadata
    )
    return success_json(created, status_code=201)


@router.post("/upload-tags", openapi_extra=IMPORT_FILE_OPENAPI)
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def upload_tags(
    request: Request,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "upload_tags")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
    settings: Settings = Depends(get_settings),
) -> Response:
    content = await read_import_upload(request, settings.import_max_bytes)
    result = await export_import.upload_knowledge_tags(session, actor=actor, access=access, content=content)
    return import_result_response(result, "知识标签-跳过明细.xlsx")


@router.get("/{file_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_item(
    file_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "read")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
) -> JSONResponse:
    return success_json(await service.get_detail(session, actor=actor, access=access, file_id=file_id))


@router.get("/{file_id}/preview")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def preview_item(
    file_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "preview")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
) -> JSONResponse:
    return success_json(await service.preview_knowledge(session, actor=actor, access=access, file_id=file_id))


@router.get("/{file_id}/content")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def get_item_content(
    file_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "preview")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
) -> Response:
    res = await service.read_file_content(session, actor=actor, access=access, file_id=file_id, for_download=False)
    return Response(
        content=res.content,
        media_type=res.media_type,
        headers={
            "Content-Disposition": _content_disposition("inline", res.filename),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{file_id}/download")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def download_item(
    file_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "download")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
) -> Response:
    res = await service.read_file_content(session, actor=actor, access=access, file_id=file_id, for_download=True)
    return Response(
        content=res.content,
        media_type=res.media_type,
        headers={
            "Content-Disposition": _content_disposition("attachment", res.filename),
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


@router.post("/{file_id}/favorite")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def favorite_item(
    file_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "favorite")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
) -> JSONResponse:
    return success_json(
        await service.toggle_favorite(session, actor=actor, access=access, file_id=file_id, favorite=True)
    )


@router.delete("/{file_id}/favorite")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def unfavorite_item(
    file_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "favorite")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
) -> JSONResponse:
    return success_json(
        await service.toggle_favorite(session, actor=actor, access=access, file_id=file_id, favorite=False)
    )


@router.get("/{file_id}/logs")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_item_logs(
    file_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "read")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
) -> JSONResponse:
    return success_json(
        await service.list_logs(session, actor=actor, access=access, file_id=file_id, page=page, page_size=page_size)
    )


@router.patch("/{file_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def update_item(
    file_id: uuid.UUID,
    body: KnowledgePatch,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "update")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
) -> JSONResponse:
    return success_json(
        await write_service.update_metadata(
            session, actor=actor, access=access, file_id=file_id, data=body.model_dump(exclude_unset=True)
        )
    )


@router.delete("/{file_id}")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def delete_item(
    file_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "delete")),
    access: KnowledgeAccess = Depends(get_knowledge_access),
) -> JSONResponse:
    return success_json(await write_service.delete_knowledge_file(session, actor=actor, access=access, file_id=file_id))
