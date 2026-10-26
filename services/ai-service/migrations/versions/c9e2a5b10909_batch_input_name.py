"""批量任务记下本次输入文件名；样本试跑与批量任务共用任务表，按来源区分

Revision ID: c9e2a5b10909
Revises: b8d1f4a90808
Create Date: 2026-10-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9e2a5b10909"
down_revision: Union[str, None] = "b8d1f4a90808"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_batch_runs",
        sa.Column("input_name", sa.String(255), nullable=False, server_default="", comment="输入文件名"),
    )
    op.create_index("ix_ai_batch_runs_source", "ai_batch_runs", ["source"])
    op.execute("COMMENT ON TABLE ai_batch_runs IS '批量任务（含定时任务和样本试跑）'")


def downgrade() -> None:
    op.execute("COMMENT ON TABLE ai_batch_runs IS '批量提问任务'")
    op.drop_index("ix_ai_batch_runs_source", table_name="ai_batch_runs")
    op.drop_column("ai_batch_runs", "input_name")
