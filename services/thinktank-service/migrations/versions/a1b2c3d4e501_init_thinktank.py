"""智库服务初始表：知识库资料、收藏、文件操作日志、出站事件

Revision ID: a1b2c3d4e501
Revises:
Create Date: 2026-11-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e501"
down_revision: Union[str, None] = None
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "thinktank_knowledge_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, comment="主键"),
        sa.Column("file_name", sa.String(500), nullable=False, comment="资料名称"),
        sa.Column("file_type", sa.String(64), nullable=False, server_default="", comment="文件类型"),
        sa.Column("operator_type", sa.String(32), nullable=False, server_default="", comment="运营商类型"),
        sa.Column("depart_affiliation", sa.String(255), nullable=False, server_default="", comment="部门归属"),
        sa.Column("industry_type", sa.String(255), nullable=False, server_default="", comment="行业类型"),
        sa.Column("app_scenario", sa.String(500), nullable=False, server_default="", comment="应用场景"),
        sa.Column("market_category", sa.String(64), nullable=False, server_default="", comment="市场类别"),
        sa.Column("product_type", sa.String(255), nullable=False, server_default="", comment="产品类型"),
        sa.Column("product_sub_type", sa.String(500), nullable=False, server_default="", comment="产品子类型"),
        sa.Column("prov_name", sa.String(64), nullable=False, server_default="", comment="省份"),
        sa.Column("data_time", sa.String(32), nullable=False, server_default="", comment="资料时间"),
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
        comment="智库知识库资料",
    )
    op.create_index("ix_thinktank_knowledge_files_file_name", "thinktank_knowledge_files", ["file_name"])
    op.create_index("ix_thinktank_kf_file_type", "thinktank_knowledge_files", ["file_type"])
    op.create_index("ix_thinktank_kf_industry_type", "thinktank_knowledge_files", ["industry_type"])
    op.create_index("ix_thinktank_kf_operator_type", "thinktank_knowledge_files", ["operator_type"])
    op.create_index("ix_thinktank_kf_prov_name", "thinktank_knowledge_files", ["prov_name"])
    op.create_index("ix_thinktank_kf_market_category", "thinktank_knowledge_files", ["market_category"])
    op.create_index("ix_thinktank_kf_is_defined", "thinktank_knowledge_files", ["is_defined"])
    op.create_index("ix_thinktank_kf_uploaded_at", "thinktank_knowledge_files", ["uploaded_at"])

    op.create_table(
        "thinktank_knowledge_favorites",
        sa.Column("user_id", sa.String(64), primary_key=True, comment="用户ID"),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("thinktank_knowledge_files.id", ondelete="CASCADE"),
            primary_key=True,
            comment="资料ID",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="收藏时间"),
        comment="知识库收藏",
    )

    op.create_table(
        "thinktank_knowledge_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, comment="主键"),
        sa.Column(
            "file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("thinktank_knowledge_files.id", ondelete="CASCADE"),
            nullable=False,
            comment="资料ID",
        ),
        sa.Column("actor_id", sa.String(64), nullable=False, comment="操作人ID"),
        sa.Column("actor_name", sa.String(128), nullable=False, comment="操作人"),
        sa.Column("op_type", sa.String(32), nullable=False, comment="操作类型"),
        sa.Column("detail", sa.Text(), nullable=False, server_default="", comment="操作明细"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="操作时间"),
        comment="知识库文件操作日志",
    )
    op.create_index("ix_thinktank_kl_file_created", "thinktank_knowledge_logs", ["file_id", "created_at"])

    op.create_table(
        "thinktank_outbox",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True, comment="事件ID"),
        sa.Column("event_type", sa.String(128), nullable=False, comment="事件类型"),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1", comment="事件结构版本"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, comment="事件内容"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending", comment="投递状态"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0", comment="重试次数"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True, comment="下次重试时间"),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True, comment="租约截止时间"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="创建时间"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="失败原因"),
        comment="智库服务出站事件",
    )
    op.create_index("ix_thinktank_outbox_status", "thinktank_outbox", ["status"])
    op.create_index("ix_thinktank_outbox_next_retry_at", "thinktank_outbox", ["next_retry_at"])


def downgrade() -> None:
    op.drop_index("ix_thinktank_outbox_next_retry_at", table_name="thinktank_outbox")
    op.drop_index("ix_thinktank_outbox_status", table_name="thinktank_outbox")
    op.drop_table("thinktank_outbox")
    op.drop_index("ix_thinktank_kl_file_created", table_name="thinktank_knowledge_logs")
    op.drop_table("thinktank_knowledge_logs")
    op.drop_table("thinktank_knowledge_favorites")
    op.drop_index("ix_thinktank_kf_uploaded_at", table_name="thinktank_knowledge_files")
    op.drop_index("ix_thinktank_kf_is_defined", table_name="thinktank_knowledge_files")
    op.drop_index("ix_thinktank_kf_market_category", table_name="thinktank_knowledge_files")
    op.drop_index("ix_thinktank_kf_prov_name", table_name="thinktank_knowledge_files")
    op.drop_index("ix_thinktank_kf_operator_type", table_name="thinktank_knowledge_files")
    op.drop_index("ix_thinktank_kf_industry_type", table_name="thinktank_knowledge_files")
    op.drop_index("ix_thinktank_kf_file_type", table_name="thinktank_knowledge_files")
    op.drop_index("ix_thinktank_knowledge_files_file_name", table_name="thinktank_knowledge_files")
    op.drop_table("thinktank_knowledge_files")
