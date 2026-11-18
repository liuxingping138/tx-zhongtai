"""本服务各表的筛选项字段。预览与搜索逻辑在 platform_common.options。"""

from __future__ import annotations

from typing import Any

from platform_common.options import OptionColumns, preview_options, search_options
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.fields import ENRICH_CHOICES
from app.domain.models import AreaCode, PolicyType, Scenario

SCENARIO_OPTION_COLUMNS: OptionColumns = {
    "industry_scenario_code": Scenario.industry_scenario_code,
    "industry_l1": Scenario.industry_l1,
    "scenario_tag": Scenario.scenario_tag,
    "customer_group_name": Scenario.customer_group_name,
    "is_new_scenario": Scenario.is_new_scenario,
}

POLICY_TYPE_OPTION_COLUMNS: OptionColumns = {
    "type_name": PolicyType.type_name,
    "seq_no": PolicyType.seq_no,
}

AREA_CODE_OPTION_COLUMNS: OptionColumns = {
    "prov_name": AreaCode.prov_name,
    "city_name": AreaCode.city_name,
    "county_name": AreaCode.county_name,
}


async def scenario_options(session: AsyncSession) -> dict[str, Any]:
    options = await preview_options(session, SCENARIO_OPTION_COLUMNS)
    # 补充状态是固定几项（系统写的），不在表上去重
    options["enrich_status"] = {"items": list(ENRICH_CHOICES), "truncated": False}
    return {"options": options}


async def policy_type_options(session: AsyncSession) -> dict[str, Any]:
    return {"options": await preview_options(session, POLICY_TYPE_OPTION_COLUMNS)}


async def area_code_options(session: AsyncSession) -> dict[str, Any]:
    return {"options": await preview_options(session, AREA_CODE_OPTION_COLUMNS)}


async def search(session: AsyncSession, columns: OptionColumns, *, field: str, keyword: str | None) -> list[str]:
    return await search_options(session, columns, field=field, keyword=keyword)


async def list_province_names(session: AsyncSession) -> list[str]:
    """省市区码表中去重后的全部省份名称（供智库等服务作为省枚举权威源）。"""

    stmt = (
        select(AreaCode.prov_name)
        .where(AreaCode.prov_name.is_not(None))
        .where(AreaCode.prov_name != "")
        .distinct()
        .order_by(AreaCode.prov_name)
    )
    return [name for name in (await session.execute(stmt)).scalars() if name]
