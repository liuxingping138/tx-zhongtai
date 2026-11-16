"""政策基础标签表加 ai_outputs：保存 AI 模板输出的全部动态字段

Revision ID: f8a9b0c1d2e4
Revises: e6f7a8b9c0d3
Create Date: 2026-11-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f8a9b0c1d2e4"
down_revision: Union[str, None] = "e6f7a8b9c0d3"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "policy_base_tags",
        sa.Column(
            "ai_outputs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="AI模板动态输出字段",
        ),
    )


def downgrade() -> None:
    op.drop_column("policy_base_tags", "ai_outputs")
