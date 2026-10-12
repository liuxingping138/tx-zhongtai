"""爬虫监测：按网站统计的采集快照与同步批次。"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from platform_common.orm_base import Base
from sqlalchemy import BigInteger, Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class CrawlerSiteDaily(Base):
    """爬虫监测：网站 × 采集日。只来自采集总表，不读规则表。

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
    """爬虫监测：网站快照。每次同步后由按天统计整体重算，页面、卡片、导出只读这张。

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


class CrawlerStatusDaily(Base):
    """爬虫监测每日状态分布，供「较上周」对比。

    每次同步后按当天快照写一行；缺的历史日期由同步从按天统计推算补齐（推算一次约 10 秒，页面不能现算）。
    """

    __tablename__ = "policy_crawler_status_daily"
    __table_args__ = {"comment": "爬虫监测每日状态分布"}

    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True, comment="统计日期")
    sites: Mapped[int] = mapped_column(Integer, nullable=False, comment="网站总数")
    normal: Mapped[int] = mapped_column(Integer, nullable=False, comment="正常网站数")
    watch: Mapped[int] = mapped_column(Integer, nullable=False, comment="关注网站数")
    stale: Mapped[int] = mapped_column(Integer, nullable=False, comment="停更网站数")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="计算时间")


class CrawlerSyncRun(Base):
    """爬虫监测同步批次，水位和中断识别都以它为准。"""

    __tablename__ = "policy_crawler_sync_runs"
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
