"""类型判断任务加「采集省份」多选：只读选中省份的源政策

已有任务为空列表（不限），和原来一样读全部省份。

Revision ID: e6f7a8b9c0d3
Revises: d5e6f7a8b9c2
Create Date: 2026-11-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e6f7a8b9c0d3"
down_revision: Union[str, None] = "d5e6f7a8b9c2"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "policy_ai_tasks",
        sa.Column(
            "provinces",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="采集省份（空为不限）",
        ),
    )


def downgrade() -> None:
    op.drop_column("policy_ai_tasks", "provinces")
