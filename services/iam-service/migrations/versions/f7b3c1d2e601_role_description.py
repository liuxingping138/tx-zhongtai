"""角色增加职责说明，分配角色时能看出该角色负责什么

Revision ID: f7b3c1d2e601
Revises: e2c04f15a301
Create Date: 2026-09-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7b3c1d2e601"
down_revision: Union[str, None] = "e2c04f15a301"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "iam_roles",
        sa.Column("description", sa.String(500), nullable=False, server_default="", comment="角色说明"),
    )


def downgrade() -> None:
    op.drop_column("iam_roles", "description")
