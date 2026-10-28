"""行业场景码表加「是否新增场景」「来源政策」：政策解读同步进来的场景单独标出来，不再借用场景来源和三级场景描述

Revision ID: b8c7d8e9f006
Revises: a7b5d6e7f904
Create Date: 2026-10-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c7d8e9f006"
down_revision: Union[str, None] = "a7b5d6e7f904"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "codebook_scenarios",
        sa.Column("is_new_scenario", sa.String(8), nullable=False, server_default="否", comment="是否新增场景"),
    )
    op.add_column(
        "codebook_scenarios",
        sa.Column("source_policy", sa.String(500), nullable=False, server_default="", comment="来源政策"),
    )


def downgrade() -> None:
    op.drop_column("codebook_scenarios", "source_policy")
    op.drop_column("codebook_scenarios", "is_new_scenario")
