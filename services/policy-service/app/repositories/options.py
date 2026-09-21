from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.domain.models import BaseTag, Interpretation, Source


async def _values(session: AsyncSession, column: InstrumentedAttribute[str], limit: int = 8000) -> list[str]:
    result = await session.execute(
        select(column).where(column.is_not(None)).where(column != "").distinct().order_by(column).limit(limit)
    )
    return [value for value in result.scalars() if value]


async def source_options(session: AsyncSession) -> dict[str, Any]:
    pairs = await session.execute(
        select(Source.province_name, Source.city_name)
        .where(Source.province_name != "")
        .where(Source.city_name != "")
        .distinct()
    )
    city_by_province: dict[str, list[str]] = {}
    for province, city in pairs:
        if province and city:
            city_by_province.setdefault(province, []).append(city)
    for cities in city_by_province.values():
        cities.sort()
    return {
        "site_name": await _values(session, Source.site_name),
        "province_name": await _values(session, Source.province_name),
        "city_name": await _values(session, Source.city_name),
        "tag": await _values(session, Source.tag),
        "crawl_priority": await _values(session, Source.crawl_priority),
        "city_by_province": city_by_province,
    }


async def base_tag_options(session: AsyncSession) -> dict[str, list[str]]:
    return {
        "policy_name": await _values(session, BaseTag.policy_name),
        "province_name": await _values(session, BaseTag.province_name),
        "policy_types": await _values(session, BaseTag.policy_types),
        "is_penetrate": await _values(session, BaseTag.is_penetrate),
        "need_interpret": await _values(session, BaseTag.need_interpret),
    }


async def interpretation_options(session: AsyncSession) -> dict[str, list[str]]:
    return {
        "policy_title": await _values(session, Interpretation.policy_title),
        "industry_scenario_code": await _values(session, Interpretation.industry_scenario_code),
        "industry_l1": await _values(session, Interpretation.industry_l1),
        "opportunity_type": await _values(session, Interpretation.opportunity_type),
    }
