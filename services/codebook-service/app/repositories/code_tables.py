"""给 AI 模板用的码表：只取模板需要的列，去重后按层级排好。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import PolicyType, Scenario
from app.repositories.policy_types import ORDER_BY as POLICY_TYPE_ORDER

SCENARIO_CODE_LOCK = 72120261022
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


async def scenario_codes(session: AsyncSession) -> list[tuple[str, tuple[str, str, str], str, tuple[str, str, str]]]:
    """全部场景行的编码和名称，用来查编码、分配新编码。8000 多行，一次读完。"""

    rows = await session.execute(
        select(Scenario.industry_code, *_SCENARIO_LEVELS[:3], Scenario.scenario_code, *_SCENARIO_LEVELS[3:])
    )
    return [
        (
            str(code or ""),
            (str(i1 or ""), str(i2 or ""), str(i3 or "")),
            str(sc or ""),
            (str(s1 or ""), str(s2 or ""), str(s3 or "")),
        )
        for code, i1, i2, i3, sc, s1, s2, s3 in rows
    ]


async def lock_scenario_codes(session: AsyncSession) -> None:
    """分配新编码要「读最大号 → 加一 → 写入」，两个同步并发会拿到同一个号。事务级锁串行化。"""

    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SCENARIO_CODE_LOCK})
