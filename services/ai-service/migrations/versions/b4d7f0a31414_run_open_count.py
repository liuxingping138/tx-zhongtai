"""批量任务记下还没答好的行数

第 2 轮或重跑途中进程被杀，只靠「已处理」「失败」两个数推，正在重问的行会算两次，「重跑失败的 N 条」偏大。
执行进程写进度时直接算好；已有的任务留空，照旧推算。

Revision ID: b4d7f0a31414
Revises: a3c6e9f21313
Create Date: 2026-10-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4d7f0a31414"
down_revision: Union[str, None] = "a3c6e9f21313"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ai_batch_runs", sa.Column("open_count", sa.Integer(), nullable=True, comment="还没答好的行数"))


def downgrade() -> None:
    op.drop_column("ai_batch_runs", "open_count")
