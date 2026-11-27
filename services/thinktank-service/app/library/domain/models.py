"""报告库与方案库 ORM 模型（各含主表、收藏表、操作日志表）。"""

from __future__ import annotations

import uuid
from datetime import datetime

from platform_common.orm_base import Base
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class ReportFile(Base):
    __tablename__ = "thinktank_report_files"
    __table_args__ = (
        Index("ix_thinktank_rf_report_name", "report_name"),
        Index("ix_thinktank_rf_customer_name", "customer_name"),
        Index("ix_thinktank_rf_report_type", "report_type"),
        Index("ix_thinktank_rf_industry_tags", "industry_tags"),
        Index("ix_thinktank_rf_region_tag", "region_tag"),
        Index("ix_thinktank_rf_delivery_dept", "delivery_dept"),
        Index("ix_thinktank_rf_is_temp_support", "is_temp_support"),
        Index("ix_thinktank_rf_delivery_date", "delivery_date"),
        Index("ix_thinktank_rf_is_defined", "is_defined"),
        Index("ix_thinktank_rf_uploaded_at", "uploaded_at"),
        {"comment": "智库报告库文件"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    report_name: Mapped[str] = mapped_column(String(500), nullable=False, comment="报告名称")
    project_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="所属项目"
    )
    customer_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="客户名称"
    )
    report_type: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", server_default="", comment="报告类型"
    )
    industry_tags: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="行业赛道标签"
    )
    region_tag: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", server_default="", comment="区域标签"
    )
    delivery_dept: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="交付部门"
    )
    participants: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default="", comment="参与人员"
    )
    is_temp_support: Mapped[str] = mapped_column(
        String(16), nullable=False, default="", server_default="", comment="是否临时支撑"
    )
    delivery_date: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", server_default="", comment="交付日期"
    )
    summary: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="核心结论摘要(≤100字)"
    )
    keywords: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default="", comment="关键词(3-5个)"
    )
    data_sources: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="主要数据来源"
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="上传时间")
    file_suffix: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", server_default="", comment="文件后缀"
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0", comment="文件大小字节"
    )
    storage_path: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default="", comment="文件存储路径"
    )
    content_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="摘要与预览文本"
    )
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="", comment="备注")
    is_defined: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", comment="是否已定义标签"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1", comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="入库时间")
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="入库人ID")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="入库人")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="更新人ID")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="操作人")


class ReportFavorite(Base):
    __tablename__ = "thinktank_report_favorites"
    __table_args__ = {"comment": "报告库收藏"}

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="用户ID")
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("thinktank_report_files.id", ondelete="CASCADE"),
        primary_key=True,
        comment="报告ID",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="收藏时间")


class ReportOpLog(Base):
    __tablename__ = "thinktank_report_logs"
    __table_args__ = (
        Index("ix_thinktank_rl_file_created", "file_id", "created_at"),
        Index("ix_thinktank_rl_created_op", "created_at", "op_type"),
        {"comment": "报告库文件操作日志"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("thinktank_report_files.id", ondelete="CASCADE"),
        nullable=False,
        comment="报告ID",
    )
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="操作人ID")
    actor_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="操作人")
    op_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="操作类型")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="", comment="操作明细")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="操作时间")


class ProposalFile(Base):
    __tablename__ = "thinktank_proposal_files"
    __table_args__ = (
        Index("ix_thinktank_pf_proposal_name", "proposal_name"),
        Index("ix_thinktank_pf_customer_name", "customer_name"),
        Index("ix_thinktank_pf_proposal_type", "proposal_type"),
        Index("ix_thinktank_pf_industry_tags", "industry_tags"),
        Index("ix_thinktank_pf_region_tag", "region_tag"),
        Index("ix_thinktank_pf_opportunity_source", "opportunity_source"),
        Index("ix_thinktank_pf_bidding_method", "bidding_method"),
        Index("ix_thinktank_pf_bid_deadline", "bid_deadline"),
        Index("ix_thinktank_pf_owner_dept", "owner_dept"),
        Index("ix_thinktank_pf_owner_name", "owner_name"),
        Index("ix_thinktank_pf_result_status", "result_status"),
        Index("ix_thinktank_pf_is_defined", "is_defined"),
        Index("ix_thinktank_pf_uploaded_at", "uploaded_at"),
        {"comment": "智库方案库文件"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    proposal_name: Mapped[str] = mapped_column(String(500), nullable=False, comment="方案名称")
    customer_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="客户名称"
    )
    proposal_type: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", server_default="", comment="方案类型"
    )
    industry_tags: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="行业赛道标签"
    )
    region_tag: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", server_default="", comment="区域标签"
    )
    opportunity_source: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", server_default="", comment="商机来源"
    )
    bidding_method: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", server_default="", comment="招标方式"
    )
    bid_deadline: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", server_default="", comment="投标截止日期"
    )
    owner_dept: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="方案负责部门"
    )
    owner_name: Mapped[str] = mapped_column(
        String(128), nullable=False, default="", server_default="", comment="方案负责人"
    )
    quote_amount: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default="", comment="报价(万元)"
    )
    result_status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default="", comment="结果"
    )
    win_amount: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default="", comment="中标金额(万元)"
    )
    selling_points: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="方案核心卖点摘要(≤100字)"
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="上传时间")
    file_suffix: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", server_default="", comment="文件后缀"
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0", comment="文件大小字节"
    )
    storage_path: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default="", comment="文件存储路径"
    )
    content_text: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default="", comment="摘要与预览文本"
    )
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="", comment="备注")
    is_defined: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", comment="是否已定义标签"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1", comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="入库时间")
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="入库人ID")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="入库人")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="更新人ID")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="操作人")


class ProposalFavorite(Base):
    __tablename__ = "thinktank_proposal_favorites"
    __table_args__ = {"comment": "方案库收藏"}

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="用户ID")
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("thinktank_proposal_files.id", ondelete="CASCADE"),
        primary_key=True,
        comment="方案ID",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="收藏时间")


class ProposalOpLog(Base):
    __tablename__ = "thinktank_proposal_logs"
    __table_args__ = (
        Index("ix_thinktank_pl_file_created", "file_id", "created_at"),
        Index("ix_thinktank_pl_created_op", "created_at", "op_type"),
        {"comment": "方案库文件操作日志"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("thinktank_proposal_files.id", ondelete="CASCADE"),
        nullable=False,
        comment="方案ID",
    )
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="操作人ID")
    actor_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="操作人")
    op_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="操作类型")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="", comment="操作明细")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="操作时间")
