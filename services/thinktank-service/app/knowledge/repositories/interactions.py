"""资料库互动仓储：用户收藏与单文件操作日志。"""

from __future__ import annotations

import uuid

from platform_common.clock import utcnow
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.domain.models import KnowledgeFavorite, KnowledgeOpLog


async def favorite_ids_for_user(
    session: AsyncSession,
    *,
    user_id: str,
    file_ids: list[uuid.UUID],
) -> set[uuid.UUID]:
    if not file_ids:
        return set()
    stmt = select(KnowledgeFavorite.file_id).where(
        KnowledgeFavorite.user_id == user_id,
        KnowledgeFavorite.file_id.in_(file_ids),
    )
    return set((await session.execute(stmt)).scalars())


async def is_favorited(session: AsyncSession, *, user_id: str, file_id: uuid.UUID) -> bool:
    stmt = select(KnowledgeFavorite.file_id).where(
        KnowledgeFavorite.user_id == user_id,
        KnowledgeFavorite.file_id == file_id,
    )
    return (await session.scalar(stmt)) is not None


async def set_favorite(session: AsyncSession, *, user_id: str, file_id: uuid.UUID, favorite: bool) -> bool:
    if favorite:
        stmt = (
            pg_insert(KnowledgeFavorite)
            .values(user_id=user_id, file_id=file_id, created_at=utcnow())
            .on_conflict_do_nothing(index_elements=["user_id", "file_id"])
            .returning(KnowledgeFavorite.file_id)
        )
        return (await session.scalar(stmt)) is not None
    del_stmt = (
        delete(KnowledgeFavorite)
        .where(
            KnowledgeFavorite.user_id == user_id,
            KnowledgeFavorite.file_id == file_id,
        )
        .returning(KnowledgeFavorite.file_id)
    )
    return (await session.scalar(del_stmt)) is not None


async def add_op_log(
    session: AsyncSession,
    *,
    file_id: uuid.UUID,
    actor_id: str,
    actor_name: str,
    op_type: str,
    detail: str = "",
) -> KnowledgeOpLog:
    row = KnowledgeOpLog(
        file_id=file_id,
        actor_id=actor_id,
        actor_name=actor_name,
        op_type=op_type,
        detail=detail,
        created_at=utcnow(),
    )
    session.add(row)
    return row


async def list_op_logs(
    session: AsyncSession,
    *,
    file_id: uuid.UUID,
    page: int,
    page_size: int,
) -> tuple[list[KnowledgeOpLog], int]:
    total = int(
        await session.scalar(select(func.count()).select_from(KnowledgeOpLog).where(KnowledgeOpLog.file_id == file_id))
        or 0
    )
    stmt = (
        select(KnowledgeOpLog)
        .where(KnowledgeOpLog.file_id == file_id)
        .order_by(KnowledgeOpLog.created_at.desc(), KnowledgeOpLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await session.execute(stmt)).scalars()), total
