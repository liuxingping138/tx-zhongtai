from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aitag.domain.models import CONFIG_ID, PolicyAiConfig, PolicyAiRun
from app.policy.domain.models import BaseTag, Interpretation


async def config(session: AsyncSession, *, lock: bool = False) -> PolicyAiConfig:
    statement = select(PolicyAiConfig).where(PolicyAiConfig.id == CONFIG_ID)
    if lock:
        statement = statement.with_for_update()
    row = (await session.scalars(statement)).first()
    if row is None:
        raise RuntimeError("缺少政策 AI 打标配置，请先执行数据库迁移")
    return row


async def spent_since(session: AsyncSession, since: datetime) -> Decimal:
    value = await session.scalar(
        select(func.coalesce(func.sum(PolicyAiRun.cost), 0)).where(PolicyAiRun.started_at >= since)
    )
    return Decimal(value or 0)


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> PolicyAiRun | None:
    return await session.get(PolicyAiRun, run_id)


async def page_runs(session: AsyncSession, page: int, page_size: int) -> tuple[list[PolicyAiRun], int]:
    total = int(await session.scalar(select(func.count()).select_from(PolicyAiRun)) or 0)
    rows = await session.scalars(
        select(PolicyAiRun).order_by(PolicyAiRun.started_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return list(rows), total


async def base_tags_by_source(session: AsyncSession, source_ids: list[str]) -> dict[str, BaseTag]:
    if not source_ids:
        return {}
    rows = await session.scalars(select(BaseTag).where(BaseTag.source_content_id.in_(source_ids)).with_for_update())
    return {str(row.source_content_id): row for row in rows}


async def base_tag_by_hash(session: AsyncSession, digest: str) -> BaseTag | None:
    return (await session.scalars(select(BaseTag).where(BaseTag.content_hash == digest))).first()


async def interpret_backlog(session: AsyncSession, limit: int) -> list[BaseTag]:
    """需要解读、还没解读过的 AI 打标政策，先打标的先解读。上一批费用到上限没做完的也在里面。"""

    rows = await session.scalars(
        select(BaseTag)
        .where(
            BaseTag.need_interpret == "是",
            BaseTag.source_content_id.is_not(None),
            BaseTag.interpreted_at.is_(None),
        )
        .order_by(BaseTag.tagged_at, BaseTag.id)
        .limit(limit)
    )
    return list(rows)


async def opportunity_backlog(session: AsyncSession, limit: int) -> list[BaseTag]:
    rows = await session.scalars(
        select(BaseTag)
        .where(BaseTag.interpreted_at.is_not(None), BaseTag.opportunity_at.is_(None))
        .order_by(BaseTag.interpreted_at, BaseTag.id)
        .limit(limit)
    )
    return list(rows)


async def base_tags_by_ids(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, BaseTag]:
    if not ids:
        return {}
    rows = await session.scalars(select(BaseTag).where(BaseTag.id.in_(ids)).with_for_update())
    return {row.id: row for row in rows}


async def ai_interpretations(session: AsyncSession, source_ids: list[str]) -> dict[str, list[Interpretation]]:
    if not source_ids:
        return {}
    rows = await session.scalars(
        select(Interpretation)
        .where(Interpretation.source_content_id.in_(source_ids))
        .order_by(Interpretation.created_at, Interpretation.id)
        .with_for_update()
    )
    grouped: dict[str, list[Interpretation]] = {}
    for row in rows:
        grouped.setdefault(str(row.source_content_id), []).append(row)
    return grouped


async def taken_relation_keys(session: AsyncSession, keys: list[str]) -> set[str]:
    if not keys:
        return set()
    return set(await session.scalars(select(Interpretation.relation_key).where(Interpretation.relation_key.in_(keys))))


async def delete_rows(session: AsyncSession, rows: list[Interpretation]) -> None:
    for row in rows:
        await session.delete(row)
