from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Interpretation


async def get_by_id(session: AsyncSession, item_id: uuid.UUID) -> Interpretation | None:
    return await session.get(Interpretation, item_id)


async def get_by_relation_key(session: AsyncSession, relation_key: str) -> Interpretation | None:
    result = await session.execute(select(Interpretation).where(Interpretation.relation_key == relation_key))
    return result.scalar_one_or_none()


async def list_relation_keys(session: AsyncSession) -> set[str]:
    result = await session.execute(select(Interpretation.relation_key))
    return set(result.scalars())


async def list_items(
    session: AsyncSession,
    *,
    policy_title: str | None,
    industry_scenario_code: str | None,
    industry_l1: str | None,
    opportunity_type: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Interpretation], int]:
    stmt = select(Interpretation)
    count_stmt = select(func.count()).select_from(Interpretation)
    filters = [
        (Interpretation.policy_title, policy_title),
        (Interpretation.industry_scenario_code, industry_scenario_code),
        (Interpretation.industry_l1, industry_l1),
        (Interpretation.opportunity_type, opportunity_type),
    ]
    for column, value in filters:
        if value:
            cond = column.ilike(f"%{value}%")
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
    total = int(await session.scalar(count_stmt) or 0)
    result = await session.execute(
        stmt.order_by(Interpretation.policy_title, Interpretation.industry_scenario_code)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars()), total


async def list_all(session: AsyncSession) -> list[Interpretation]:
    result = await session.execute(
        select(Interpretation).order_by(Interpretation.policy_title, Interpretation.industry_scenario_code)
    )
    return list(result.scalars())
