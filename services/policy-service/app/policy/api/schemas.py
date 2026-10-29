from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class SourceClearRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: str


class SourceStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    crawler_status: str = Field(min_length=1, max_length=64)


class InterpretationStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    data_status: str = Field(min_length=1, max_length=32)


class SourceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int | None = None
    province_name: str = ""
    province_code: str = ""
    city_name: str = ""
    city_code: str = ""
    district_name: str = ""
    district_code: str = ""
    site_name: str
    site_type: str = ""
    crawler_status: str = ""
    # 日期框点清除给的是 null：要能清空，不能回 422「Input should be a valid string」。
    online_date: str | None = ""
    crawl_priority: str = ""
    url: str = ""
    tag: str = ""
    data_type: str = ""
    department: str = ""


class BaseTagWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int | None = None
    policy_name: str
    issuing_dept: str = ""
    issuer_industry: str = ""
    policy_level: str = ""
    province_code: str = ""
    province_name: str = ""
    city_code: str = ""
    city_name: str = ""
    issued_at: str = ""
    policy_types: str = ""
    source_url: str = ""
    is_penetrate: str = ""
    penetrate_words: str = ""
    penetrate_score: str = ""
    need_interpret: str = ""
    remark: str = ""


class InterpretationWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int | None = None
    tenant_id: str = ""
    policy_uid: str = ""
    policy_title: str
    industry_scenario_code: str = ""
    industry_code: str = ""
    industry_l1: str = ""
    industry_l2: str = ""
    industry_l3: str = ""
    scenario_code: str = ""
    scenario_l1_name: str = ""
    scenario_l2_name: str = ""
    scenario_l3_name: str = ""
    target_customers: str = ""
    adapted_products: str = ""
    purchase_reason: str = ""
    opportunity_type: str = ""
    policy_summary: str = ""
    has_subsidy: str = ""
    subsidy_content: str = ""
    market_opportunity: str = ""
    info_level: str = ""
    is_new_scenario: str = ""
    new_scenario_level: str = ""
    remark: str = ""
    data_status: str = ""


class SourcePatch(SourceWrite):
    """仅修改显式提供的字段；空字符串表示显式清空。"""

    version: int = Field(ge=1)
    site_name: str = ""


class BaseTagPatch(BaseTagWrite):
    """仅修改显式提供的字段；空字符串表示显式清空。"""

    version: int = Field(ge=1)
    policy_name: str = ""


class InterpretationPatch(InterpretationWrite):
    """仅修改显式提供的字段；空字符串表示显式清空。"""

    version: int = Field(ge=1)
    policy_title: str = ""
