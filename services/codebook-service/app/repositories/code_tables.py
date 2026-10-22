"""给 AI 模板用的码表：只取模板需要的列，去重后按层级排好。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import PolicyType, Scenario
from app.repositories.policy_types import ORDER_BY as POLICY_TYPE_ORDER

_SCENARIO_LEVELS = (
    Scenario.industry_l1,
    Scenario.industry_l2,
    Scenario.industry_l3,
    Scenario.scenario_l1_name,
    Scenario.scenario_l2_name,
    Scenario.scenario_l3_name,
)


async def policy_types(session: AsyncSession) -> list[tuple[Any, ...]]:
    rows = await session.execute(
        select(PolicyType.type_name, PolicyType.definition, PolicyType.priority).order_by(*POLICY_TYPE_ORDER)
    )
    return [tuple(row) for row in rows]


async def scenarios(session: AsyncSession) -> list[tuple[Any, ...]]:
    rows = await session.execute(select(*_SCENARIO_LEVELS).distinct().order_by(*_SCENARIO_LEVELS))
    return [tuple(row) for row in rows]


async def scenario_l1(session: AsyncSession) -> list[tuple[Any, ...]]:
    columns = (Scenario.industry_l1, Scenario.scenario_l1_name)
    rows = await session.execute(select(*columns).where(Scenario.scenario_l1_name != "").distinct().order_by(*columns))
    return [tuple(row) for row in rows]
