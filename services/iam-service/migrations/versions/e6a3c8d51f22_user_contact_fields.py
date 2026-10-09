"""用户加电话、邮箱，只做记录展示

Revision ID: e6a3c8d51f22
Revises: d5f2b7c40e11
Create Date: 2026-10-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6a3c8d51f22"
down_revision: Union[str, None] = "d5f2b7c40e11"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "iam_users",
        sa.Column("phone", sa.String(length=32), nullable=False, server_default="", comment="电话"),
    )
    op.add_column(
        "iam_users",
        sa.Column("email", sa.String(length=254), nullable=False, server_default="", comment="邮箱"),
    )


def downgrade() -> None:
    op.drop_column("iam_users", "email")
    op.drop_column("iam_users", "phone")
