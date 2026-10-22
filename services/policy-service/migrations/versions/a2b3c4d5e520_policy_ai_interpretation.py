"""政策解读补适配产品、目标客户采买理由、备注，记 AI 来源和新增场景同步时间；基础标签记解读、市场机会进度

Revision ID: a2b3c4d5e520
Revises: f1a2b3c4d419
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from alembic import op

revision = "a2b3c4d5e520"
down_revision = "f1a2b3c4d419"
branch_labels = None
depends_on = None

_INTERPRETATION_TEXT = (("adapted_products", "适配产品"), ("purchase_reason", "目标客户采买理由"), ("remark", "备注"))


def upgrade():
    for name, comment in _INTERPRETATION_TEXT:
        op.add_column(
            "policy_interpretations", sa.Column(name, sa.Text(), nullable=False, server_default="", comment=comment)
        )
    op.add_column(
        "policy_interpretations", sa.Column("source_content_id", sa.String(200), nullable=True, comment="源政策ID")
    )
    op.add_column(
        "policy_interpretations",
        sa.Column("tagged_at", sa.DateTime(timezone=True), nullable=True, comment="AI解读时间"),
    )
    op.add_column(
        "policy_interpretations",
        sa.Column("scenario_synced_at", sa.DateTime(timezone=True), nullable=True, comment="新增场景同步进码表的时间"),
    )
    op.create_index(
        "ix_policy_interpretations_source_content_id", "policy_interpretations", ["source_content_id"]
    )
    op.add_column(
        "policy_base_tags",
        sa.Column("interpreted_at", sa.DateTime(timezone=True), nullable=True, comment="AI解读时间"),
    )
    op.add_column(
        "policy_base_tags",
        sa.Column("opportunity_at", sa.DateTime(timezone=True), nullable=True, comment="AI市场机会时间"),
    )


def downgrade():
    op.drop_column("policy_base_tags", "opportunity_at")
    op.drop_column("policy_base_tags", "interpreted_at")
    op.drop_index("ix_policy_interpretations_source_content_id", table_name="policy_interpretations")
    for name in ("scenario_synced_at", "tagged_at", "source_content_id", *(name for name, _ in _INTERPRETATION_TEXT)):
        op.drop_column("policy_interpretations", name)
