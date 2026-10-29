"""角色之外单独给人授权

Revision ID: d8f1a6c3e905
Revises: c9d4e2a7b310
Create Date: 2026-10-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d8f1a6c3e905"
down_revision: Union[str, None] = "c9d4e2a7b310"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "iam_user_grants",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, comment="用户ID"),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False, comment="资源ID"),
        sa.Column("level", sa.String(length=8), nullable=False, comment="授权级别"),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True, comment="更新人ID"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="更新时间"),
        sa.ForeignKeyConstraint(["user_id"], ["iam_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resource_id"], ["iam_resources.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("user_id", "resource_id"),
        comment="用户单独授权",
    )


def downgrade() -> None:
    op.drop_table("iam_user_grants")
