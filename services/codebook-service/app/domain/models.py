from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any

from platform_common.orm_base import Base
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.fields import AREA_CODE_COLUMNS, POLICY_TYPE_COLUMNS, SCENARIO_COLUMNS


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def content_hash(values: dict[str, str], fields: tuple[str, ...]) -> str:
    payload = {key: values.get(key, "") for key in fields}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class PolicyType(Base):
    __tablename__ = "codebook_policy_types"
    __table_args__ = (
        UniqueConstraint("type_name", name="uq_codebook_policy_types_name"),
        {"comment": "政策类型码表"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    seq_no: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="序号")
    type_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="政策类型")
    definition: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="定义")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="入库时间")
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="入库人ID")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="入库人")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="更新人ID")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="操作人")


class Scenario(Base):
    __tablename__ = "codebook_scenarios"
    __table_args__ = {"comment": "行业场景码表"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="内容哈希")
    industry_scenario_code: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", index=True, comment="行业场景编码"
    )
    industry_code: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="行业编码")
    industry_l1: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", index=True, comment="项目一级行业"
    )
    industry_l2: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="项目二级行业")
    industry_l3: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="项目三级行业")
    scenario_tag: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True, comment="场景标签")
    scenario_level: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="场景level")
    scenario_type: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="场景类型")
    desc_90: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="场景描述(90字)")
    desc_130: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="场景描述(130字)")
    desc_pest: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="场景描述(PEST总结)")
    scenario_source: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="场景来源")
    scenario_hierarchy: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="场景层级")
    scenario_code: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="场景编码")
    scenario_l1_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="项目一级场景名称")
    scenario_l1_desc: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="项目一级场景描述")
    scenario_l2_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="项目二级场景名称")
    scenario_l2_desc: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="项目二级场景描述")
    scenario_l3_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="项目三级场景名称")
    scenario_l3_desc: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="项目三级场景描述")
    customer_group_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", index=True, comment="客群名称"
    )
    customer_group_industry: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="客群行业")
    org_keywords: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="机构及企业名称包含关键词")
    scope_keywords: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="经营范围包含")
    customer_level: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="客户等级")
    customer_category: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="客户类别")
    product_l1_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="项目一级产品名称")
    product_l2_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="项目二级产品名称")
    branch_count: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="下属分支机构数")
    product_l1_sort: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="一级产品排序（正序）")
    product_l2_sort: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="二级产品排序（正序）")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="入库时间")
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="入库人ID")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="入库人")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="更新人ID")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="操作人")

    def business_values(self) -> dict[str, str]:
        return {spec.field: str(getattr(self, spec.field) or "") for spec in SCENARIO_COLUMNS}

    def refresh_hash(self) -> None:
        self.content_hash = content_hash(self.business_values(), tuple(spec.field for spec in SCENARIO_COLUMNS))


class AreaCode(Base):
    __tablename__ = "codebook_area_codes"
    __table_args__ = (
        UniqueConstraint("county_id", name="uq_codebook_area_codes_county_id"),
        {"comment": "省市区编码表"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    prov_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="省份编码")
    prov_name: Mapped[str] = mapped_column(String(200), nullable=False, default="", index=True, comment="省份名称")
    city_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="城市编码")
    city_name: Mapped[str] = mapped_column(String(200), nullable=False, default="", index=True, comment="城市名称")
    county_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="区县编码")
    county_name: Mapped[str] = mapped_column(String(200), nullable=False, default="", index=True, comment="区县名称")
    alias_prov_name: Mapped[str] = mapped_column(String(200), nullable=False, default="", comment="省份别名")
    alias_city_name: Mapped[str] = mapped_column(String(200), nullable=False, default="", comment="城市别名")
    alias_county_name: Mapped[str] = mapped_column(String(200), nullable=False, default="", comment="区县别名")
    city_name_short: Mapped[str] = mapped_column(String(200), nullable=False, default="", comment="城市简称")
    county_name_short: Mapped[str] = mapped_column(String(200), nullable=False, default="", comment="区县简称")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="入库时间")
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="入库人ID")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="入库人")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="更新人ID")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="操作人")

    def business_values(self) -> dict[str, str]:
        return {spec.field: str(getattr(self, spec.field) or "") for spec in AREA_CODE_COLUMNS}


class OutboxEvent(Base):
    __tablename__ = "codebook_outbox"
    __table_args__ = {"comment": "码表服务出站事件"}

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="事件ID")
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, comment="事件类型")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="事件结构版本")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, comment="事件内容")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True, comment="投递状态")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="重试次数")
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, comment="下次重试时间"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
    lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="租约截止时间"
    )


POLICY_TYPE_FIELDS = tuple(spec.field for spec in POLICY_TYPE_COLUMNS)
SCENARIO_FIELDS = tuple(spec.field for spec in SCENARIO_COLUMNS)
AREA_CODE_FIELDS = tuple(spec.field for spec in AREA_CODE_COLUMNS)
