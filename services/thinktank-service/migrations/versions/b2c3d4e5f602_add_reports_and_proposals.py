"""新增智库报告库与方案库表（主表、收藏表、操作日志表）

Revision ID: b2c3d4e5f602
Revises: a1b2c3d4e501
Create Date: 2026-11-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2c3d4e5f602"
down_revision: Union[str, None] = "a1b2c3d4e501"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "thinktank_report_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, comment="主键"),
        sa.Column("report_name", sa.String(500), nullable=False, comment="报告名称"),
        sa.Column("project_name", sa.String(255), nullable=False, server_default="", comment="所属项目"),
        sa.Column("customer_name", sa.String(255), nullable=False, server_default="", comment="客户名称"),
        sa.Column("report_type", sa.String(128), nullable=False, server_default="", comment="报告类型"),
        sa.Column("industry_tags", sa.String(255), nullable=False, server_default="", comment="行业赛道标签"),
        sa.Column("region_tag", sa.String(128), nullable=False, server_default="", comment="区域标签"),
        sa.Column("delivery_dept", sa.String(255), nullable=False, server_default="", comment="交付部门"),
        sa.Column("participants", sa.String(500), nullable=False, server_default="", comment="参与人员"),
        sa.Column("is_temp_support", sa.String(16), nullable=False, server_default="", comment="是否临时支撑"),
        sa.Column("delivery_date", sa.String(32), nullable=False, server_default="", comment="交付日期"),
        sa.Column("summary", sa.Text(), nullable=False, server_default="", comment="核心结论摘要(≤100字)"),
        sa.Column("keywords", sa.String(500), nullable=False, server_default="", comment="关键词(3-5个)"),
        sa.Column("data_sources", sa.Text(), nullable=False, server_default="", comment="主要数据来源"),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, comment="上传时间"),
        sa.Column("file_suffix", sa.String(32), nullable=False, server_default="", comment="文件后缀"),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False, server_default="0", comment="文件大小字节"),
        sa.Column("storage_path", sa.String(500), nullable=False, server_default="", comment="文件存储路径"),
        sa.Column("content_text", sa.Text(), nullable=False, server_default="", comment="摘要与预览文本"),
        sa.Column("remark", sa.Text(), nullable=False, server_default="", comment="备注"),
        sa.Column("is_defined", sa.Boolean(), nullable=False, server_default=sa.false(), comment="是否已定义标签"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1", comment="版本号"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="入库时间"),
        sa.Column("created_by_id", sa.String(64), nullable=False, comment="入库人ID"),
        sa.Column("created_by_name", sa.String(128), nullable=False, comment="入库人"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="更新时间"),
        sa.Column("updated_by_id", sa.String(64), nullable=False, comment="更新人ID"),
        sa.Column("updated_by_name", sa.String(128), nullable=False, comment="操作人"),
        comment="智库报告库文件",
    )
    op.create_index("ix_thinktank_rf_report_name", "thinktank_report_files", ["report_name"])
    op.create_index("ix_thinktank_rf_customer_name", "thinktank_report_files", ["customer_name"])
    op.create_index("ix_thinktank_rf_report_type", "thinktank_report_files", ["report_type"])
    op.create_index("ix_thinktank_rf_industry_tags", "thinktank_report_files", ["industry_tags"])
    op.create_index("ix_thinktank_rf_region_tag", "thinktank_report_files", ["region_tag"])
    op.create_index("ix_thinktank_rf_delivery_dept", "thinktank_report_files", ["delivery_dept"])
    op.create_index("ix_thinktank_rf_is_temp_support", "thinktank_report_files", ["is_temp_support"])
    op.create_index("ix_thinktank_rf_delivery_date", "thinktank_report_files", ["delivery_date"])
    op.create_index("ix_thinktank_rf_is_defined", "thinktank_report_files", ["is_defined"])
    op.create_index("ix_thinktank_rf_uploaded_at", "thinktank_report_files", ["uploaded_at"])

    op.create_table(
        "thinktank_report_favorites",
        sa.Column("user_id", sa.String(64), primary_key=True, comment="用户ID"),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("thinktank_report_files.id", ondelete="CASCADE"),
            primary_key=True,
            comment="报告ID",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="收藏时间"),
        comment="报告库收藏",
    )

    op.create_table(
        "thinktank_report_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, comment="主键"),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("thinktank_report_files.id", ondelete="CASCADE"),
            nullable=False,
            comment="报告ID",
        ),
        sa.Column("actor_id", sa.String(64), nullable=False, comment="操作人ID"),
        sa.Column("actor_name", sa.String(128), nullable=False, comment="操作人"),
        sa.Column("op_type", sa.String(32), nullable=False, comment="操作类型"),
        sa.Column("detail", sa.Text(), nullable=False, server_default="", comment="操作明细"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="操作时间"),
        comment="报告库文件操作日志",
    )
    op.create_index("ix_thinktank_rl_file_created", "thinktank_report_logs", ["file_id", "created_at"])

    op.create_table(
        "thinktank_proposal_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, comment="主键"),
        sa.Column("proposal_name", sa.String(500), nullable=False, comment="方案名称"),
        sa.Column("customer_name", sa.String(255), nullable=False, server_default="", comment="客户名称"),
        sa.Column("proposal_type", sa.String(128), nullable=False, server_default="", comment="方案类型"),
        sa.Column("industry_tags", sa.String(255), nullable=False, server_default="", comment="行业赛道标签"),
        sa.Column("region_tag", sa.String(128), nullable=False, server_default="", comment="区域标签"),
        sa.Column("opportunity_source", sa.String(128), nullable=False, server_default="", comment="商机来源"),
        sa.Column("bidding_method", sa.String(128), nullable=False, server_default="", comment="招标方式"),
        sa.Column("bid_deadline", sa.String(32), nullable=False, server_default="", comment="投标截止日期"),
        sa.Column("owner_dept", sa.String(255), nullable=False, server_default="", comment="方案负责部门"),
        sa.Column("owner_name", sa.String(128), nullable=False, server_default="", comment="方案负责人"),
        sa.Column("quote_amount", sa.String(64), nullable=False, server_default="", comment="报价(万元)"),
        sa.Column("result_status", sa.String(64), nullable=False, server_default="", comment="结果"),
        sa.Column("win_amount", sa.String(64), nullable=False, server_default="", comment="中标金额(万元)"),
        sa.Column("selling_points", sa.Text(), nullable=False, server_default="", comment="方案核心卖点摘要(≤100字)"),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False, comment="上传时间"),
        sa.Column("file_suffix", sa.String(32), nullable=False, server_default="", comment="文件后缀"),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False, server_default="0", comment="文件大小字节"),
        sa.Column("storage_path", sa.String(500), nullable=False, server_default="", comment="文件存储路径"),
        sa.Column("content_text", sa.Text(), nullable=False, server_default="", comment="摘要与预览文本"),
        sa.Column("remark", sa.Text(), nullable=False, server_default="", comment="备注"),
        sa.Column("is_defined", sa.Boolean(), nullable=False, server_default=sa.false(), comment="是否已定义标签"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1", comment="版本号"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="入库时间"),
        sa.Column("created_by_id", sa.String(64), nullable=False, comment="入库人ID"),
        sa.Column("created_by_name", sa.String(128), nullable=False, comment="入库人"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="更新时间"),
        sa.Column("updated_by_id", sa.String(64), nullable=False, comment="更新人ID"),
        sa.Column("updated_by_name", sa.String(128), nullable=False, comment="操作人"),
        comment="智库方案库文件",
    )
    op.create_index("ix_thinktank_pf_proposal_name", "thinktank_proposal_files", ["proposal_name"])
    op.create_index("ix_thinktank_pf_customer_name", "thinktank_proposal_files", ["customer_name"])
    op.create_index("ix_thinktank_pf_proposal_type", "thinktank_proposal_files", ["proposal_type"])
    op.create_index("ix_thinktank_pf_industry_tags", "thinktank_proposal_files", ["industry_tags"])
    op.create_index("ix_thinktank_pf_region_tag", "thinktank_proposal_files", ["region_tag"])
    op.create_index("ix_thinktank_pf_opportunity_source", "thinktank_proposal_files", ["opportunity_source"])
    op.create_index("ix_thinktank_pf_bidding_method", "thinktank_proposal_files", ["bidding_method"])
    op.create_index("ix_thinktank_pf_bid_deadline", "thinktank_proposal_files", ["bid_deadline"])
    op.create_index("ix_thinktank_pf_owner_dept", "thinktank_proposal_files", ["owner_dept"])
    op.create_index("ix_thinktank_pf_owner_name", "thinktank_proposal_files", ["owner_name"])
    op.create_index("ix_thinktank_pf_result_status", "thinktank_proposal_files", ["result_status"])
    op.create_index("ix_thinktank_pf_is_defined", "thinktank_proposal_files", ["is_defined"])
    op.create_index("ix_thinktank_pf_uploaded_at", "thinktank_proposal_files", ["uploaded_at"])

    op.create_table(
        "thinktank_proposal_favorites",
        sa.Column("user_id", sa.String(64), primary_key=True, comment="用户ID"),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("thinktank_proposal_files.id", ondelete="CASCADE"),
            primary_key=True,
            comment="方案ID",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="收藏时间"),
        comment="方案库收藏",
    )

    op.create_table(
        "thinktank_proposal_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, comment="主键"),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("thinktank_proposal_files.id", ondelete="CASCADE"),
            nullable=False,
            comment="方案ID",
        ),
        sa.Column("actor_id", sa.String(64), nullable=False, comment="操作人ID"),
        sa.Column("actor_name", sa.String(128), nullable=False, comment="操作人"),
        sa.Column("op_type", sa.String(32), nullable=False, comment="操作类型"),
        sa.Column("detail", sa.Text(), nullable=False, server_default="", comment="操作明细"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="操作时间"),
        comment="方案库文件操作日志",
    )
    op.create_index("ix_thinktank_pl_file_created", "thinktank_proposal_logs", ["file_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_thinktank_pl_file_created", table_name="thinktank_proposal_logs")
    op.drop_table("thinktank_proposal_logs")
    op.drop_table("thinktank_proposal_favorites")
    op.drop_index("ix_thinktank_pf_uploaded_at", table_name="thinktank_proposal_files")
    op.drop_index("ix_thinktank_pf_is_defined", table_name="thinktank_proposal_files")
    op.drop_index("ix_thinktank_pf_result_status", table_name="thinktank_proposal_files")
    op.drop_index("ix_thinktank_pf_owner_name", table_name="thinktank_proposal_files")
    op.drop_index("ix_thinktank_pf_owner_dept", table_name="thinktank_proposal_files")
    op.drop_index("ix_thinktank_pf_bid_deadline", table_name="thinktank_proposal_files")
    op.drop_index("ix_thinktank_pf_bidding_method", table_name="thinktank_proposal_files")
    op.drop_index("ix_thinktank_pf_opportunity_source", table_name="thinktank_proposal_files")
    op.drop_index("ix_thinktank_pf_region_tag", table_name="thinktank_proposal_files")
    op.drop_index("ix_thinktank_pf_industry_tags", table_name="thinktank_proposal_files")
    op.drop_index("ix_thinktank_pf_proposal_type", table_name="thinktank_proposal_files")
    op.drop_index("ix_thinktank_pf_customer_name", table_name="thinktank_proposal_files")
    op.drop_index("ix_thinktank_pf_proposal_name", table_name="thinktank_proposal_files")
    op.drop_table("thinktank_proposal_files")

    op.drop_index("ix_thinktank_rl_file_created", table_name="thinktank_report_logs")
    op.drop_table("thinktank_report_logs")
    op.drop_table("thinktank_report_favorites")
    op.drop_index("ix_thinktank_rf_uploaded_at", table_name="thinktank_report_files")
    op.drop_index("ix_thinktank_rf_is_defined", table_name="thinktank_report_files")
    op.drop_index("ix_thinktank_rf_delivery_date", table_name="thinktank_report_files")
    op.drop_index("ix_thinktank_rf_is_temp_support", table_name="thinktank_report_files")
    op.drop_index("ix_thinktank_rf_delivery_dept", table_name="thinktank_report_files")
    op.drop_index("ix_thinktank_rf_region_tag", table_name="thinktank_report_files")
    op.drop_index("ix_thinktank_rf_industry_tags", table_name="thinktank_report_files")
    op.drop_index("ix_thinktank_rf_report_type", table_name="thinktank_report_files")
    op.drop_index("ix_thinktank_rf_customer_name", table_name="thinktank_report_files")
    op.drop_index("ix_thinktank_rf_report_name", table_name="thinktank_report_files")
    op.drop_table("thinktank_report_files")
