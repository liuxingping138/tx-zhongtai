"""基础标签表加默认排序索引：province_code, policy_name, id

Revision ID: b1c2d3e4f5a6
Revises: a9b0c1d2e3f5
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a9b0c1d2e3f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_policy_base_tags_default_order",
            "policy_base_tags",
            ["province_code", "policy_name", "id"],
            unique=False,
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_policy_base_tags_default_order",
            table_name="policy_base_tags",
            postgresql_concurrently=True,
            if_exists=True,
        )
