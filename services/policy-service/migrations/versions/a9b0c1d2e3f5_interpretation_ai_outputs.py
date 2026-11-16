"""政策解读表加 ai_outputs：保存解读与市场机会模板新增的动态输出字段

Revision ID: a9b0c1d2e3f5
Revises: f8a9b0c1d2e4
Create Date: 2026-11-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a9b0c1d2e3f5"
down_revision: Union[str, None] = "f8a9b0c1d2e4"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "policy_interpretations",
        sa.Column(
            "ai_outputs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="AI模板动态输出字段",
        ),
    )


def downgrade() -> None:
    op.drop_column("policy_interpretations", "ai_outputs")
