from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PolicyTypeWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq_no: str = ""
    type_name: str
    definition: str = ""
    version: int | None = None


class ScenarioWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int | None = None
    industry_scenario_code: str = ""
    industry_code: str = ""
    industry_l1: str = ""
    industry_l2: str = ""
    industry_l3: str = ""
    scenario_tag: str = ""
    scenario_level: str = ""
    scenario_type: str = ""
    desc_90: str = ""
    desc_130: str = ""
    desc_pest: str = ""
    scenario_source: str = ""
    scenario_hierarchy: str = ""
    scenario_code: str = ""
    scenario_l1_name: str = ""
    scenario_l1_desc: str = ""
    scenario_l2_name: str = ""
    scenario_l2_desc: str = ""
    scenario_l3_name: str = ""
    scenario_l3_desc: str = ""
    customer_group_name: str = ""
    customer_group_industry: str = ""
    org_keywords: str = ""
    scope_keywords: str = ""
    customer_level: str = ""
    customer_category: str = ""
    product_l1_name: str = ""
    product_l2_name: str = ""
    branch_count: str = ""
    product_l1_sort: str = ""
    product_l2_sort: str = ""


class AreaCodeWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int | None = None
    prov_id: str = ""
    prov_name: str = ""
    city_id: str = ""
    city_name: str = ""
    county_id: str = ""
    county_name: str = ""
    alias_prov_name: str = ""
    alias_city_name: str = ""
    alias_county_name: str = ""
    city_name_short: str = ""
    county_name_short: str = ""


class PolicyTypePatch(PolicyTypeWrite):
    """仅修改显式提供的字段；空字符串表示显式清空。"""

    version: int = Field(ge=1)
    type_name: str = ""


class ScenarioPatch(ScenarioWrite):
    """仅修改显式提供的字段；空字符串表示显式清空。"""

    version: int = Field(ge=1)


class AreaCodePatch(AreaCodeWrite):
    """仅修改显式提供的字段；空字符串表示显式清空。"""

    version: int = Field(ge=1)
