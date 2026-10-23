"""政策基础标签可以勾选「重新判断类型」：记下请求时间，下次类型判断先重打这些

Revision ID: f7a8b9c0d035
Revises: e6f7a8b9c924
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "f7a8b9c0d035"
down_revision = "e6f7a8b9c924"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "policy_base_tags",
        sa.Column("type_retag_at", sa.DateTime(timezone=True), nullable=True, comment="重新判断类型的请求时间"),
    )
    op.create_index(
        "ix_policy_base_tags_type_retag_at",
        "policy_base_tags",
        ["type_retag_at"],
        postgresql_where=sa.text("type_retag_at IS NOT NULL"),
    )


def downgrade():
    op.drop_index("ix_policy_base_tags_type_retag_at", table_name="policy_base_tags")
    op.drop_column("policy_base_tags", "type_retag_at")
