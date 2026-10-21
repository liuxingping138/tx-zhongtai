"""本服务各表的筛选项字段。预览与搜索逻辑在 platform_common.options。"""

from __future__ import annotations

from typing import Any

from platform_common.options import OptionColumns, preview_options, search_options
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.policy.domain.fields import DATA_STATUS_CHOICES
from app.policy.domain.models import BaseTag, Interpretation, Source

SOURCE_OPTION_COLUMNS: OptionColumns = {
    "site_name": Source.site_name,
    "province_name": Source.province_name,
    "city_name": Source.city_name,
    "tag": Source.tag,
    "crawl_priority": Source.crawl_priority,
    "site_type": Source.site_type,
    "crawler_status": Source.crawler_status,
}

BASE_TAG_OPTION_COLUMNS: OptionColumns = {
    "policy_name": BaseTag.policy_name,
    "province_name": BaseTag.province_name,
    "policy_types": BaseTag.policy_types,
    "is_penetrate": BaseTag.is_penetrate,
    "need_interpret": BaseTag.need_interpret,
}

INTERPRETATION_OPTION_COLUMNS: OptionColumns = {
    "policy_title": Interpretation.policy_title,
    "industry_scenario_code": Interpretation.industry_scenario_code,
    "industry_l1": Interpretation.industry_l1,
    "scenario_l1_name": Interpretation.scenario_l1_name,
    "opportunity_type": Interpretation.opportunity_type,
    "is_new_scenario": Interpretation.is_new_scenario,
    "new_scenario_level": Interpretation.new_scenario_level,
    "info_level": Interpretation.info_level,
    "data_status": Interpretation.data_status,
}


async def source_options(session: AsyncSession) -> dict[str, Any]:
    # 省份数量有限，省市联动表整份下发；地市字段本身仍可能被截断。
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
        "options": await preview_options(session, SOURCE_OPTION_COLUMNS),
        "city_by_province": city_by_province,
    }


async def base_tag_options(session: AsyncSession) -> dict[str, Any]:
    return {"options": await preview_options(session, BASE_TAG_OPTION_COLUMNS)}


async def interpretation_options(session: AsyncSession) -> dict[str, Any]:
    options = await preview_options(session, INTERPRETATION_OPTION_COLUMNS)
    # 数据状态是固定两项：取库里去重值的话，还没有人工验证的数据时下拉里就选不到它。
    options["data_status"] = {"items": list(DATA_STATUS_CHOICES), "truncated": False}
    return {"options": options}


async def search(session: AsyncSession, columns: OptionColumns, *, field: str, keyword: str | None) -> list[str]:
    return await search_options(session, columns, field=field, keyword=keyword)
