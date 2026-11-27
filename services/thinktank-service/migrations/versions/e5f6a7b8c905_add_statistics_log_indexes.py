"""为三库操作日志表补 (created_at, op_type) 联合索引，支撑智库统计行为趋势与排行榜查询

Revision ID: e5f6a7b8c905
Revises: d4e5f6a7b804
Create Date: 2026-11-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e5f6a7b8c905"
down_revision: str | None = "d4e5f6a7b804"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES: tuple[tuple[str, str], ...] = (
    ("ix_thinktank_kl_created_op", "thinktank_knowledge_logs"),
    ("ix_thinktank_rl_created_op", "thinktank_report_logs"),
    ("ix_thinktank_pl_created_op", "thinktank_proposal_logs"),
)


def upgrade() -> None:
    for idx_name, table in _INDEXES:
        op.create_index(idx_name, table, ["created_at", "op_type"])


def downgrade() -> None:
    for idx_name, table in _INDEXES:
        op.drop_index(idx_name, table_name=table)
