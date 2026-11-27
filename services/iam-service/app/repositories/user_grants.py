"""用户单独授权的读写。"""

from __future__ import annotations

import uuid

from platform_common.clock import utcnow
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import NodeType
from app.domain.models import Resource, UserGrant
from app.domain.thinktank_catalog import THINKTANK_DOWNLOAD_CODES


async def list_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[tuple[str, str]]:
    """这个人单独授权的（模块编码, 档位），只含已发布的叶子模块。"""

    result = await session.execute(
        select(Resource.code, UserGrant.level)
        .join(UserGrant, UserGrant.resource_id == Resource.id)
        .where(
            UserGrant.user_id == user_id,
            Resource.published.is_(True),
            Resource.node_type == NodeType.RESOURCE,
        )
        .order_by(Resource.sort_order)
    )
    return [(code, str(level)) for code, level in result.all()]


async def replace_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    grants: list[tuple[uuid.UUID, str]],
    *,
    updated_by: uuid.UUID | None,
) -> None:
    await session.execute(delete(UserGrant).where(UserGrant.user_id == user_id))
    now = utcnow()
    for resource_id, level in grants:
        session.add(
            UserGrant(user_id=user_id, resource_id=resource_id, level=level, updated_by=updated_by, updated_at=now)
        )
    await session.flush()


async def clear_for_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(delete(UserGrant).where(UserGrant.user_id == user_id))


async def count_by_users(session: AsyncSession, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not user_ids:
        return {}
    result = await session.execute(
        select(UserGrant.user_id, func.count())
        .join(Resource, Resource.id == UserGrant.resource_id)
        .where(
            UserGrant.user_id.in_(user_ids),
            Resource.published.is_(True),
            Resource.node_type == NodeType.RESOURCE,
            ~Resource.code.startswith("thinktank.file_type."),
            ~Resource.code.startswith("thinktank.industry_type."),
            ~Resource.code.in_(THINKTANK_DOWNLOAD_CODES),
        )
        .group_by(UserGrant.user_id)
    )
    return {user_id: int(count) for user_id, count in result.all()}
