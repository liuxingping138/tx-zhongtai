"""批量任务可以跑模板草稿：记下跑的是哪次保存的草稿（跑上线版本时为空，看上线版本号）

Revision ID: d0f3b6c21010
Revises: c9e2a5b10909
Create Date: 2026-10-28
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d0f3b6c21010"
down_revision: Union[str, None] = "c9e2a5b10909"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_batch_runs",
        sa.Column("draft_saved_at", sa.DateTime(timezone=True), nullable=True, comment="草稿保存时间"),
    )


def downgrade() -> None:
    op.drop_column("ai_batch_runs", "draft_saved_at")
