from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Scenario


async def get_by_id(session: AsyncSession, item_id: uuid.UUID) -> Scenario | None:
    return await session.get(Scenario, item_id)


async def get_by_hash(session: AsyncSession, digest: str) -> Scenario | None:
    result = await session.execute(select(Scenario).where(Scenario.content_hash == digest))
    return result.scalar_one_or_none()


async def list_items(
    session: AsyncSession,
    *,
    industry_scenario_code: str | None,
    industry_l1: str | None,
    scenario_tag: str | None,
    customer_group_name: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Scenario], int]:
    stmt = select(Scenario)
    count_stmt = select(func.count()).select_from(Scenario)
    filters = [
        (Scenario.industry_scenario_code, industry_scenario_code),
        (Scenario.industry_l1, industry_l1),
        (Scenario.scenario_tag, scenario_tag),
        (Scenario.customer_group_name, customer_group_name),
    ]
    for column, value in filters:
        if value:
            cond = column.ilike(f"%{value}%")
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
    total = int(await session.scalar(count_stmt) or 0)
    result = await session.execute(
        stmt.order_by(Scenario.industry_scenario_code, Scenario.scenario_tag)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars()), total


async def count_all(session: AsyncSession) -> int:
    """导出前先数行数，避免把超限的整表读进内存。"""

    return int(await session.scalar(select(func.count()).select_from(Scenario)) or 0)


async def list_all(session: AsyncSession) -> list[Scenario]:
    result = await session.execute(select(Scenario).order_by(Scenario.industry_scenario_code, Scenario.scenario_tag))
    return list(result.scalars())
