"""知识库接口请求体模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class KnowledgePatch(BaseModel):
    """编辑知识库资料标签与名称；version 用于并发冲突校验。"""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    file_name: str | None = None
    file_type: str | None = None
    operator_type: str | None = None
    depart_affiliation: str | None = None
    industry_type: str | None = None
    app_scenario: str | None = None
    market_category: str | None = None
    product_type: str | None = None
    product_sub_type: str | None = None
    prov_name: str | None = None
    data_time: str | None = None
    remark: str | None = None
