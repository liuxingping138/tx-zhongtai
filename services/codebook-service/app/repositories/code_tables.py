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


async def scenario_nodes(
    session: AsyncSession,
) -> list[tuple[tuple[str, str, str], tuple[str, str, str], tuple[str, str, str], str]]:
    """场景节点和描述，给新增场景审核看同级场景、找相似场景。按客群重复的行去重后读。"""

    rows = await session.execute(
        select(
            *_SCENARIO_LEVELS,
            Scenario.scenario_l1_desc,
            Scenario.scenario_l2_desc,
            Scenario.scenario_l3_desc,
            Scenario.desc_90,
        ).distinct()
    )
    return [
        (
            (str(i1 or ""), str(i2 or ""), str(i3 or "")),
            (str(s1 or "").strip(), str(s2 or "").strip(), str(s3 or "").strip()),
            (str(d1 or ""), str(d2 or ""), str(d3 or "")),
            str(d90 or ""),
        )
        for i1, i2, i3, s1, s2, s3, d1, d2, d3, d90 in rows
    ]


def _path_conditions(path: tuple[str, ...]) -> list[Any]:
    return [column == name for column, name in zip(_SCENARIO_LEVELS[3:], path, strict=False)]


async def rows_with_path(session: AsyncSession, path: tuple[str, ...], *, lock: bool) -> list[Scenario]:
    """场景路径以 path 开头的全部行（各行业、各客群），改名要一起改。"""

    statement = select(Scenario).where(*_path_conditions(path)).order_by(Scenario.id)
    if lock:
        statement = statement.with_for_update()
    return list(await session.scalars(statement))


async def rows_with_enrich(
    session: AsyncSession, status: str, *, lock: bool, path: tuple[str, ...] = ()
) -> list[Scenario]:
    """补充状态是 status 的行（可只取一个场景路径的），按路径排好。新增场景几百个以内。"""

    conds = [Scenario.enrich_status == status]
    if path:
        conds.extend(_path_conditions(path))
        conds.extend(column == "" for column in _SCENARIO_LEVELS[3 + len(path) :])
    statement = select(Scenario).where(*conds).order_by(*_SCENARIO_LEVELS[3:], Scenario.id)
    if lock:
        statement = statement.with_for_update()
    return list(await session.scalars(statement))


async def path_exists(session: AsyncSession, path: tuple[str, ...]) -> bool:
    found = await session.scalar(select(Scenario.id).where(*_path_conditions(path)).limit(1))
    return found is not None


async def lock_scenario_codes(session: AsyncSession) -> None:
    """分配新编码要「读最大号 → 加一 → 写入」，两个同步并发会拿到同一个号。事务级锁串行化。"""

    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SCENARIO_CODE_LOCK})
