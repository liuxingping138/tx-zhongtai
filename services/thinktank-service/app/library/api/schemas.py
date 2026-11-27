"""报告库与方案库请求体与查询筛选依赖。"""

from __future__ import annotations

from fastapi import Query
from platform_common.filters import Filters
from pydantic import BaseModel, ConfigDict, Field


class ReportPatch(BaseModel):
    """编辑报告库元数据；version 用于乐观锁并发冲突校验。"""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    report_name: str | None = None
    project_name: str | None = None
    customer_name: str | None = None
    report_type: str | None = None
    industry_tags: str | None = None
    region_tag: str | None = None
    delivery_dept: str | None = None
    participants: str | None = None
    is_temp_support: str | None = None
    delivery_date: str | None = None
    summary: str | None = None
    keywords: str | None = None
    data_sources: str | None = None
    remark: str | None = None


class ProposalPatch(BaseModel):
    """编辑方案库元数据；version 用于乐观锁并发冲突校验。"""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    proposal_name: str | None = None
    customer_name: str | None = None
    proposal_type: str | None = None
    industry_tags: str | None = None
    region_tag: str | None = None
    opportunity_source: str | None = None
    bidding_method: str | None = None
    bid_deadline: str | None = None
    owner_dept: str | None = None
    owner_name: str | None = None
    quote_amount: str | None = None
    result_status: str | None = None
    win_amount: str | None = None
    selling_points: str | None = None
    remark: str | None = None


def report_filters(
    report_name: list[str] | None = Query(default=None),
    project_name: list[str] | None = Query(default=None),
    customer_name: list[str] | None = Query(default=None),
    report_type: list[str] | None = Query(default=None),
    industry_tags: list[str] | None = Query(default=None),
    region_tag: list[str] | None = Query(default=None),
    delivery_dept: list[str] | None = Query(default=None),
    participants: list[str] | None = Query(default=None),
    is_temp_support: list[str] | None = Query(default=None),
    delivery_date: list[str] | None = Query(default=None),
    keywords: list[str] | None = Query(default=None),
    tag_status: list[str] | None = Query(default=None),
    favorite_only: list[str] | None = Query(default=None),
) -> Filters:
    return {
        "report_name": report_name,
        "project_name": project_name,
        "customer_name": customer_name,
        "report_type": report_type,
        "industry_tags": industry_tags,
        "region_tag": region_tag,
        "delivery_dept": delivery_dept,
        "participants": participants,
        "is_temp_support": is_temp_support,
        "delivery_date": delivery_date,
        "keywords": keywords,
        "tag_status": tag_status,
        "favorite_only": favorite_only,
    }


def proposal_filters(
    proposal_name: list[str] | None = Query(default=None),
    customer_name: list[str] | None = Query(default=None),
    proposal_type: list[str] | None = Query(default=None),
    industry_tags: list[str] | None = Query(default=None),
    region_tag: list[str] | None = Query(default=None),
    opportunity_source: list[str] | None = Query(default=None),
    bidding_method: list[str] | None = Query(default=None),
    bid_deadline: list[str] | None = Query(default=None),
    owner_dept: list[str] | None = Query(default=None),
    owner_name: list[str] | None = Query(default=None),
    result_status: list[str] | None = Query(default=None),
    tag_status: list[str] | None = Query(default=None),
    favorite_only: list[str] | None = Query(default=None),
) -> Filters:
    return {
        "proposal_name": proposal_name,
        "customer_name": customer_name,
        "proposal_type": proposal_type,
        "industry_tags": industry_tags,
        "region_tag": region_tag,
        "opportunity_source": opportunity_source,
        "bidding_method": bidding_method,
        "bid_deadline": bid_deadline,
        "owner_dept": owner_dept,
        "owner_name": owner_name,
        "result_status": result_status,
        "tag_status": tag_status,
        "favorite_only": favorite_only,
    }
