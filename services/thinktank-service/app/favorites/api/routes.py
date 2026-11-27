"""智库统一「我的收藏」路由。"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from platform_common.actors import Actor
from platform_common.authz import AuthzClient
from platform_common.enums import SecurityClass
from platform_common.http_utils import success_json
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.security import classified, fetch_scope_levels, get_authz_client, require_thinktank_permission
from app.core.database import get_db_session
from app.favorites.application import favorites as service
from app.favorites.domain.access import ALL_FAVORITES_SCOPE_RESOURCES, FavoritesAccess, FavoritesQuery

router = APIRouter(prefix="/api/v1/thinktank/favorites", tags=["thinktank-favorites"])
RESOURCE = "thinktank.favorites"


async def get_favorites_access(
    request: Request,
    client: Annotated[AuthzClient, Depends(get_authz_client)],
) -> FavoritesAccess:
    """实时拉取当前用户在资料库（含二维范围）、报告库、方案库上的有效授权。"""

    levels = await fetch_scope_levels(request, client, ALL_FAVORITES_SCOPE_RESOURCES, "list")
    return FavoritesAccess.from_levels(levels)


@router.get("")
@classified(SecurityClass.RESOURCE_AUTHORIZED)
async def list_my_favorites(
    library: Literal["all", "knowledge", "reports", "proposals"] = Query(default="all"),
    keyword: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: Actor = Depends(require_thinktank_permission(RESOURCE, "list")),
    access: FavoritesAccess = Depends(get_favorites_access),
) -> JSONResponse:
    return success_json(
        await service.list_favorites(
            session,
            actor=actor,
            access=access,
            query=FavoritesQuery(library=library, keyword=keyword, page=page, page_size=page_size),
        )
    )
