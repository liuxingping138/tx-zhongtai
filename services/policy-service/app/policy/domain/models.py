"""政策三表：信源、基础标签、解读。"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime

from platform_common.orm_base import Base
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.policy.domain.fields import BASE_TAG_COLUMNS


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def content_hash(values: dict[str, str], fields: tuple[str, ...]) -> str:
    payload = {key: values.get(key, "") for key in fields}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


class Source(Base):
    __tablename__ = "policy_sources"
    __table_args__ = (
        UniqueConstraint("internal_id", name="uq_policy_sources_internal_id"),
        UniqueConstraint("site_code", name="uq_policy_sources_site_code"),
        {"comment": "信源管理"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    internal_id: Mapped[str] = mapped_column(String(32), nullable=False, comment="内部唯一id")
    site_code: Mapped[str] = mapped_column(String(16), nullable=False, comment="网站编码")
    province_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="省份")
    province_code: Mapped[str] = mapped_column(String(8), nullable=False, default="", index=True, comment="省份编码")
    city_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="地市")
    city_code: Mapped[str] = mapped_column(String(8), nullable=False, default="", index=True, comment="地市编码")
    district_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="区县")
    district_code: Mapped[str] = mapped_column(String(8), nullable=False, default="", index=True, comment="区县编码")
    site_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True, comment="网站名称")
    site_type: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="网站类型"
    )
    crawler_status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default="", comment="爬虫状态"
    )
    # 统一存成 YYYY-MM-DD 文本，没填为空串；和其他字段一样按文本导入导出。
    online_date: Mapped[str] = mapped_column(
        String(10), nullable=False, default="", server_default="", comment="上线时间"
    )
    crawl_priority: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", comment="网站梳理和抓取的优先级"
    )
    url: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="链接")
    tag: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="标签")
    data_type: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="数据类型")
    department: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="所属部门")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="入库时间")
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="入库人ID")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="入库人")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="更新人ID")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="操作人")


class BaseTag(Base):
    __tablename__ = "policy_base_tags"
    __table_args__ = {"comment": "政策基础标签表"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="内容哈希")
    policy_name: Mapped[str] = mapped_column(Text, nullable=False, default="", index=True, comment="政策名称")
    issuing_dept: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="出台部门")
    issuer_industry: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="发文机构行业")
    policy_level: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="政策层级")
    province_code: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="省份编码")
    province_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True, comment="省份名称")
    city_code: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="地市编码")
    city_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="地市名称")
    issued_at: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="当前政策出台时间")
    policy_types: Mapped[str] = mapped_column(Text, nullable=False, default="", index=True, comment="政策类型")
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="原始网站链接")
    is_penetrate: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="是否穿透")
    penetrate_words: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="穿透词")
    penetrate_score: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="穿透词评分")
    need_interpret: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="是否解读")
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="备注")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="入库时间")
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="入库人ID")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="入库人")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="更新人ID")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="操作人")

    def business_values(self) -> dict[str, str]:
        return {spec.field: str(getattr(self, spec.field) or "") for spec in BASE_TAG_COLUMNS}

    def refresh_hash(self) -> None:
        self.content_hash = content_hash(self.business_values(), tuple(spec.field for spec in BASE_TAG_COLUMNS))


class Interpretation(Base):
    __tablename__ = "policy_interpretations"
    __table_args__ = (
        UniqueConstraint("relation_key", name="uq_policy_interpretations_relation_key"),
        {"comment": "政策解读列表"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    record_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="自增或雪花算法")
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="租户ID")
    policy_uid: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True, comment="政策唯一标识")
    policy_title: Mapped[str] = mapped_column(Text, nullable=False, default="", index=True, comment="政策原文名称")
    industry_scenario_code: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", index=True, comment="行业场景编码"
    )
    industry_code: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="行业编码")
    industry_l1: Mapped[str] = mapped_column(String(128), nullable=False, default="", index=True, comment="一级行业")
    industry_l2: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="二级行业")
    industry_l3: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="三级行业")
    scenario_code: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="场景编码")
    scenario_l1_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="一级场景名称")
    scenario_l2_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="二级场景名称")
    scenario_l3_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="三级场景名称")
    target_customers: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="目标客户当前政策影响客户群"
    )
    relation_key: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="关联主键")
    opportunity_type: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="机会类型")
    policy_summary: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="政策要文")
    has_subsidy: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="有无政府补贴")
    subsidy_content: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="补贴内容")
    market_opportunity: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="政策市场机会")
    info_level: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="信息化等级")
    is_new_scenario: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="是否新增场景")
    new_scenario_level: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="新增场景级别")
    data_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="待验证", server_default="待验证", comment="数据状态"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="入库时间")
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="入库人ID")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="入库人")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="更新人ID")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="操作人")


SOURCE_FIELDS = (
    "province_name",
    "province_code",
    "city_name",
    "city_code",
    "district_name",
    "district_code",
    "site_name",
    "site_type",
    "crawler_status",
    "online_date",
    "crawl_priority",
    "url",
    "tag",
    "data_type",
    "department",
)
BASE_TAG_FIELDS = tuple(spec.field for spec in BASE_TAG_COLUMNS)
INTERPRETATION_WRITE_FIELDS = (
    "tenant_id",
    "policy_uid",
    "policy_title",
    "industry_scenario_code",
    "industry_code",
    "industry_l1",
    "industry_l2",
    "industry_l3",
    "scenario_code",
    "scenario_l1_name",
    "scenario_l2_name",
    "scenario_l3_name",
    "target_customers",
    "opportunity_type",
    "policy_summary",
    "has_subsidy",
    "subsidy_content",
    "market_opportunity",
    "info_level",
    "is_new_scenario",
    "new_scenario_level",
    "data_status",
)
