from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.domain.models import AreaCode, PolicyType, Scenario


async def _values(session: AsyncSession, column: InstrumentedAttribute[str], limit: int = 8000) -> list[str]:
    result = await session.execute(
        select(column).where(column.is_not(None)).where(column != "").distinct().order_by(column).limit(limit)
    )
    return [value for value in result.scalars() if value]


async def scenario_options(session: AsyncSession) -> dict[str, list[str]]:
    return {
        "industry_scenario_code": await _values(session, Scenario.industry_scenario_code),
        "industry_l1": await _values(session, Scenario.industry_l1),
        "scenario_tag": await _values(session, Scenario.scenario_tag),
        "customer_group_name": await _values(session, Scenario.customer_group_name),
    }


async def policy_type_options(session: AsyncSession) -> dict[str, list[str]]:
    return {
        "type_name": await _values(session, PolicyType.type_name),
        "seq_no": await _values(session, PolicyType.seq_no),
    }


async def area_code_options(session: AsyncSession) -> dict[str, list[str]]:
    return {
        "prov_name": await _values(session, AreaCode.prov_name),
        "city_name": await _values(session, AreaCode.city_name),
        "county_name": await _values(session, AreaCode.county_name),
    }
