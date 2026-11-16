"""政策三表：信源、基础标签、解读。"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime

from platform_common.orm_base import Base
from sqlalchemy import ColumnElement, DateTime, Index, Integer, String, Text, UniqueConstraint, and_, literal, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.policy.domain.fields import BASE_TAG_COLUMNS

YES = "是"


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
        # 网站编码标识网站，按栏目展开后同一个网站有几行共用一个编码（见 crawlconfig.domain.expand），不再唯一。
        Index("ix_policy_sources_site_code", "site_code"),
        # 一条规则只展开成一行。
        Index("uq_policy_sources_rule_id", "rule_id", unique=True, postgresql_where=text("rule_id <> ''")),
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
    # 爬虫配置同步见过的这个网站最早那条规则的创建日期（YYYY-MM-DD），空 = 同步还没见过它的规则。
    # 不进 Excel、不在页面上：只用来分清上线时间是规则定的（只往前挪）还是导入时填的（对齐成规则日期）。
    rule_date: Mapped[str] = mapped_column(
        String(10), nullable=False, default="", server_default="", comment="规则最早创建日期"
    )
    # 按栏目展开的行对应的爬虫规则（规则表的 id），空 = 按网站一行的老数据或人工建的行。不进 Excel。
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="", comment="规则ID")
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
    __table_args__ = (
        UniqueConstraint("source_content_id", name="uq_policy_base_tags_source_content_id"),
        # 打标流水线的三类待办只给待办的行建索引（部分索引），几百万行时任务调度页每 5 秒数待办、每批取待办都不扫整表。
        # 条件和 awaiting_interpretation / awaiting_opportunity 一字不差，改一边要改另一边。
        Index(
            "ix_policy_base_tags_type_retag_at",
            "type_retag_at",
            postgresql_where=text("type_retag_at IS NOT NULL"),
        ),
        Index(
            "ix_policy_base_tags_interpret_backlog",
            "tagged_at",
            "id",
            postgresql_where=text("need_interpret = '是' AND source_content_id IS NOT NULL AND interpreted_at IS NULL"),
        ),
        Index(
            "ix_policy_base_tags_opportunity_backlog",
            "interpreted_at",
            "id",
            postgresql_where=text("interpreted_at IS NOT NULL AND opportunity_at IS NULL"),
        ),
        # 「是否穿透」「是否解读」的筛选项是去重值：有索引就只读索引，不读几个 G 的整表。
        # 是否穿透是人填的，AI 行都空着，只给填了的行建。
        Index("ix_policy_base_tags_need_interpret", "need_interpret"),
        Index("ix_policy_base_tags_is_penetrate", "is_penetrate", postgresql_where=text("is_penetrate <> ''")),
        # 政策名称按关键词模糊查找（ILIKE '%词%'），三个字及以上走这个三元组索引。
        Index(
            "ix_policy_base_tags_policy_name_trgm",
            "policy_name",
            postgresql_using="gin",
            postgresql_ops={"policy_name": "gin_trgm_ops"},
        ),
        # 一条政策可以有多个类型（如「信息化建设类、产业发展类」），按类型筛选是包含匹配，也走三元组索引。
        Index(
            "ix_policy_base_tags_policy_types_trgm",
            "policy_types",
            postgresql_using="gin",
            postgresql_ops={"policy_types": "gin_trgm_ops"},
        ),
        {"comment": "政策基础标签表"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="内容哈希")
    policy_name: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="政策名称")
    issuing_dept: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="出台部门")
    issuer_industry: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="发文机构行业")
    policy_level: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="政策层级")
    province_code: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="省份编码")
    province_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True, comment="省份名称")
    city_code: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="地市编码")
    city_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="地市名称")
    issued_at: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="当前政策出台时间")
    policy_types: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="政策类型")
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="原始网站链接")
    is_penetrate: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="是否穿透")
    penetrate_words: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="穿透词")
    penetrate_score: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="穿透词评分")
    need_interpret: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="是否解读")
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="备注")
    ai_outputs: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"), comment="AI模板动态输出字段"
    )
    # AI 打标写入的行带源政策 ID，重打同一条政策时按它更新，不按内容哈希新增一行。手工导入的行为空。
    source_content_id: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="源政策ID")
    tagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="AI打标时间")
    # 打标流水线的后两步按这两个时间找待办：需要解读但还没解读的、解读了还没做市场机会的。
    interpreted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="AI解读时间"
    )
    opportunity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="AI市场机会时间"
    )
    # 在列表上勾选「重新判断类型」的时间：下次类型判断先重打这些，打完清空。
    type_retag_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="重新判断类型的请求时间"
    )
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
        # 还没和码表比对过的行：AI 每批写完、导入后按它补比对，几百万行里只有刚写进来的几行。
        # 条件和 unclassified_interpretation 一字不差。
        Index("ix_policy_interpretations_unclassified", "id", postgresql_where=text("scenario_state = ''")),
        Index(
            "ix_policy_interpretations_policy_title_trgm",
            "policy_title",
            postgresql_using="gin",
            postgresql_ops={"policy_title": "gin_trgm_ops"},
        ),
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
    scenario_l1_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", index=True, comment="一级场景名称"
    )
    scenario_l2_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="二级场景名称")
    scenario_l3_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="三级场景名称")
    target_customers: Mapped[str] = mapped_column(
        Text, nullable=False, default="", comment="目标客户当前政策影响客户群"
    )
    adapted_products: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="适配产品")
    purchase_reason: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="目标客户采买理由")
    relation_key: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="关联主键")
    opportunity_type: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="机会类型")
    policy_summary: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="政策要文")
    has_subsidy: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="有无政府补贴")
    subsidy_content: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="补贴内容")
    market_opportunity: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="政策市场机会")
    info_level: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="信息化等级")
    is_new_scenario: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="是否新增场景")
    new_scenario_level: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="新增场景级别")
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="备注")
    ai_outputs: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"), comment="AI模板动态输出字段"
    )
    # AI 解读写入的行带源政策 ID；手工录入、导入的为空。重新解读同一条政策时按它清掉没人动过的旧行。
    source_content_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True, comment="源政策ID")
    tagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="AI解读时间")
    scenario_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="新增场景同步进码表的时间"
    )
    data_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="待验证", server_default="待验证", comment="数据状态"
    )
    # 和码表比对的结果（见 fields.SCENARIO_STATE_*）；新增场景归到哪个候选。系统写，不进 Excel。
    scenario_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="", server_default="", index=True, comment="场景状态"
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True, comment="新增场景候选ID"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="入库时间")
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="入库人ID")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="入库人")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="更新人ID")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="操作人")


# 下面几个条件要用上对应的部分索引：常量直接写进 SQL（literal_execute）。写成绑定参数的话，
# PostgreSQL 换成通用执行计划后证明不了查询落在部分索引的范围里，又会退回整表扫描。
def _const(value: str) -> ColumnElement[str]:
    return literal(value, String(), literal_execute=True)


def awaiting_interpretation() -> ColumnElement[bool]:
    """待解读：需要解读、还没解读的 AI 打标行。"""

    return and_(
        BaseTag.need_interpret == _const(YES), BaseTag.source_content_id.is_not(None), BaseTag.interpreted_at.is_(None)
    )


def awaiting_opportunity() -> ColumnElement[bool]:
    """待补市场机会：解读过、还没补市场机会。"""

    return and_(BaseTag.interpreted_at.is_not(None), BaseTag.opportunity_at.is_(None))


def unclassified_interpretation() -> ColumnElement[bool]:
    """还没和行业场景码表比对过的解读行。"""

    return Interpretation.scenario_state == _const("")


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
    "adapted_products",
    "purchase_reason",
    "opportunity_type",
    "policy_summary",
    "has_subsidy",
    "subsidy_content",
    "market_opportunity",
    "info_level",
    "is_new_scenario",
    "new_scenario_level",
    "remark",
    "data_status",
)
