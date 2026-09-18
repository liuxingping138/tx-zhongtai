from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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

