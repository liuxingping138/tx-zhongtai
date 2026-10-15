"""批量任务记录格式不对的条数，和调用失败分开显示

Revision ID: c3e6a9b40303
Revises: b2d5f8a30202
Create Date: 2026-10-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3e6a9b40303"
down_revision: Union[str, None] = "b2d5f8a30202"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_batch_runs",
        sa.Column("format_failed_count", sa.Integer(), nullable=False, server_default="0", comment="格式不对条数"),
    )


def downgrade() -> None:
    op.drop_column("ai_batch_runs", "format_failed_count")
