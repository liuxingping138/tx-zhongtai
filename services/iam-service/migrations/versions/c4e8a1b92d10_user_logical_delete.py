"""用户逻辑删除后可以重新使用同名用户名

Revision ID: c4e8a1b92d10
Revises: a8c4d2e3f702
Create Date: 2026-10-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8a1b92d10"
down_revision: Union[str, None] = "a8c4d2e3f702"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_iam_users_username", "iam_users", type_="unique")
    op.create_index(
        "uq_iam_users_username_live",
        "iam_users",
        ["username"],
        unique=True,
        postgresql_where=sa.text("status <> 'deleted'"),
    )


def downgrade() -> None:
    op.drop_index("uq_iam_users_username_live", table_name="iam_users")
    op.create_unique_constraint("uq_iam_users_username", "iam_users", ["username"])
