from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime
from typing import Any

from platform_common.orm_base import Base
from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.fields import BASE_TAG_COLUMNS


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
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="入库时间")
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="入库人ID")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="入库人")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="更新人ID")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="操作人")


class CrawlerTask(Base):
    """爬虫任务基线，来源是爬虫库 `policy_rules_alls_spider` 的规则配置。

    一个网站有几十个标签，每个标签一条规则，也就是监测的最小单位。
    """

    __tablename__ = "policy_crawler_tasks"
    __table_args__ = (
        UniqueConstraint("correlation", name="uq_policy_crawler_tasks_correlation"),
        {"comment": "政策爬虫任务基线"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    correlation: Mapped[str] = mapped_column(String(64), nullable=False, comment="爬虫规则唯一ID")
    # 实测网站编码格式不统一（11 位数字、GYQ、3200000000A 都有），不能按 11 位定长。
    site_key: Mapped[str] = mapped_column(String(128), nullable=False, comment="网站内部关联键")
    site_code: Mapped[str] = mapped_column(String(100), nullable=False, default="", index=True, comment="网站编码")
    # 这张表只被健康快照重算按 (site_code, tag) 关联，没有按名称/省份查的场景，不建索引。
    site_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="网站名称")
    province_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="省份名称")
    city_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="地市名称")
    tag: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="标签")
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="栏目源链接")
    rule_state: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="爬虫规则状态")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="同步时间")


class CrawlerDailyStat(Base):
    """任务 × 自然日 的采集量。页面所有趋势和健康度都从这张表算，不回查爬虫库。

    这是派生事实表，不是业务记录：没有任何代码按 id 引用它，每次同步都按
    (采集日期, 网站内部关联键, 标签) 覆盖写。UUID 主键索引实测零命中，还要在每次
    upsert 时维护，所以不跟其它业务表一样用 UUID，直接用这组天然键做主键。
    """

    __tablename__ = "policy_crawler_daily_stats"
    __table_args__ = {"comment": "政策爬虫按天采集统计"}

    collect_date: Mapped[date] = mapped_column(Date, primary_key=True, index=True, comment="采集日期")
    site_key: Mapped[str] = mapped_column(String(128), primary_key=True, comment="网站内部关联键")
    site_code: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", index=True, comment="网站编码"
    )
    site_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="网站名称")
    # 页面按省份筛的是健康快照表，这张事实表没有按省份查的场景，不建索引。
    province_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="省份名称")
    city_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="地市名称")
    tag: Mapped[str] = mapped_column(String(255), primary_key=True, nullable=False, default="", comment="标签")
    identity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="网站关联是否已校验")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="采集条数")
    named_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="有政策名称条数")
    content_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="有正文条数")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="同步时间")


class CrawlerTaskHealth(Base):
    """任务健康快照，每次同步后整体重算。页面主列表直接查这张表。

    停更判定按任务（网站+标签）而不是按网站：实测同一个网站不同标签的停更程度差别
    很大（有的标签昨天还在出数、有的停了两个月），只看站级会把半死的站显示成正常。
    """

    __tablename__ = "policy_crawler_task_health"
    __table_args__ = (
        UniqueConstraint("site_key", "tag", name="uq_policy_crawler_task_health_key"),
        {"comment": "政策爬虫任务健康快照"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    site_key: Mapped[str] = mapped_column(String(128), nullable=False, comment="网站内部关联键")
    site_code: Mapped[str] = mapped_column(String(100), nullable=False, default="", index=True, comment="网站编码")
    # 这三列是页面列表的筛选字段（省份、地市、网站名称），保留索引。
    site_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", index=True, comment="网站名称")
    province_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True, comment="省份名称")
    city_name: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="地市名称")
    tag: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="标签")
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="栏目源链接")
    last_collect_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="最后采集日期")
    stale_days: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True, comment="停更天数")
    count_7d: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="近7天采集条数")
    count_30d: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="近30天采集条数")
    count_90d: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="近90天采集条数")
    count_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="统计窗口内累计条数")
    health_status: Mapped[str] = mapped_column(String(16), nullable=False, index=True, comment="健康状态")
    in_rules: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="爬虫规则表是否仍有配置")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="快照计算时间")


class CrawlerSyncRun(Base):
    """同步批次留痕，用于判断页面数字是哪一次同步产生的、有没有同步失败。"""

    __tablename__ = "policy_crawler_sync_runs"
    __table_args__ = {"comment": "政策爬虫同步批次"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="结束时间")
    date_from: Mapped[date] = mapped_column(Date, nullable=False, comment="同步起始日期")
    date_to: Mapped[date] = mapped_column(Date, nullable=False, comment="同步截止日期")
    task_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="同步任务基线行数")
    stat_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="写入按天统计行数")
    health_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="重算健康快照行数")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running", comment="批次状态")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
    # 下次同步的起点：本批次在爬虫库见到的最大入库时间。按它找出「哪些采集日被动过」，
    # 再整天重算，这样迟到入库的数据不会因为固定天数窗口滑过去而永久漏算。
    watermark: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="已同步到的入库时间水位"
    )


class CrawlerSiteDaily(Base):
    """爬虫监测 v2：网站 × 采集日。只来自采集总表，不读规则表。

    网站身份是「网站名称 + 省份 + 地市」的原始值，不做别名归一。同步按采集日整天替换，
    所以删数据、重复同步都不会让累计量偏掉；这张表只供汇总，页面不直接读。
    """

    __tablename__ = "policy_crawler_site_daily"
    __table_args__ = {"comment": "爬虫监测网站按天统计"}

    collect_date: Mapped[date] = mapped_column(Date, primary_key=True, comment="采集日期")
    site_name: Mapped[str] = mapped_column(String(255), primary_key=True, comment="网站名称")
    province_name: Mapped[str] = mapped_column(String(64), primary_key=True, comment="省份")
    city_name: Mapped[str] = mapped_column(String(64), primary_key=True, comment="地市")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="数据条数")
    last_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最新数据入库时间"
    )
    last_published_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="最近数据发布日期")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="同步时间")


class CrawlerSite(Base):
    """爬虫监测 v2：网站快照。每次同步后由按天统计整体重算，页面、卡片、导出只读这张。

    只有几千行，筛选又都是模糊匹配，除唯一键外不建索引。
    """

    __tablename__ = "policy_crawler_sites"
    __table_args__ = (
        UniqueConstraint("site_name", "province_name", "city_name", name="uq_policy_crawler_sites_identity"),
        {"comment": "爬虫监测网站快照"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    site_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="网站名称")
    province_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="省份")
    city_name: Mapped[str] = mapped_column(String(64), nullable=False, comment="地市")
    total_rows: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, comment="数据总量")
    last_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最新数据入库时间"
    )
    last_published_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="最近数据发布日期")
    # 按最新入库日期算：反映爬虫多久没抓到新数据，而不是网站多久没发文。
    stale_days: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="停更天数")
    status: Mapped[str] = mapped_column(String(16), nullable=False, comment="监测状态")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="快照计算时间")


class CrawlerV2SyncRun(Base):
    """爬虫监测 v2 同步批次。与 v1 的批次表分开，两套并存期间水位互不干扰。"""

    __tablename__ = "policy_crawler_v2_sync_runs"
    __table_args__ = {"comment": "爬虫监测同步批次"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    mode: Mapped[str] = mapped_column(String(16), nullable=False, comment="同步方式")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="结束时间")
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True, comment="重算起始采集日")
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True, comment="重算截止采集日")
    days_synced: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="重算天数")
    site_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="网站快照行数")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running", comment="批次状态")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
    watermark: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="已同步到的入库时间水位"
    )


class OutboxEvent(Base):
    __tablename__ = "policy_outbox"
    __table_args__ = {"comment": "政策服务出站事件"}

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


SOURCE_FIELDS = (
    "province_name",
    "province_code",
    "city_name",
    "city_code",
    "district_name",
    "district_code",
    "site_name",
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
)

# 注册调度模型，供 Alembic 与元数据校验发现。
from app.domain.scheduler_models import ScheduledJob, ScheduledRun, SchedulerHeartbeat  # noqa: E402, F401
