"""模板和批量任务加「模板类型」（政策、客户、招投标），按类型授权和筛选

已有模板和历史任务都记作政策类，需要的在页面上改。

Revision ID: e5a8c1d60505
Revises: d4f7b0c50404
Create Date: 2026-10-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5a8c1d60505"
down_revision: Union[str, None] = "d4f7b0c50404"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_prompt_templates",
        sa.Column("category", sa.String(16), nullable=False, server_default="policy", comment="模板类型"),
    )
    op.add_column(
        "ai_batch_runs",
        sa.Column("prompt_category", sa.String(16), nullable=False, server_default="policy", comment="模板类型"),
    )


def downgrade() -> None:
    op.drop_column("ai_batch_runs", "prompt_category")
    op.drop_column("ai_prompt_templates", "category")
