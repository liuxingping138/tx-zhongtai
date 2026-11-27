"""访问白名单：限定公司网络的模块（智库），管理员给某个人按 IP 开有时效的白名单

Revision ID: a1f2e3d4c506
Revises: e3b7c2d9f114
Create Date: 2026-11-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1f2e3d4c506"
down_revision: Union[str, None] = "e3b7c2d9f114"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "iam_ip_whitelist",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, comment="主键"),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, comment="用户ID"),
        sa.Column("ip_range", sa.String(length=64), nullable=False, comment="IP或网段"),
        sa.Column("reason", sa.String(length=500), nullable=False, server_default="", comment="开通原因"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, comment="到期时间"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False, comment="开通人ID"),
        sa.Column("created_by_name", sa.String(length=128), nullable=False, comment="开通人"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="开通时间"),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=False, comment="最后修改人ID"),
        sa.Column("updated_by_name", sa.String(length=128), nullable=False, comment="最后修改人"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="最后修改时间"),
        sa.ForeignKeyConstraint(["user_id"], ["iam_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="访问白名单",
    )
    op.create_index("ix_iam_ip_whitelist_user_expires", "iam_ip_whitelist", ["user_id", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_iam_ip_whitelist_user_expires", table_name="iam_ip_whitelist")
    op.drop_table("iam_ip_whitelist")
