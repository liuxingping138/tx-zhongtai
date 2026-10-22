"""试发和多轮对话也记用量和费用（不记内容），费用账单把它们和批量提问、定时打标合在一起看

Revision ID: b8d1f4a90808
Revises: a7c0e3f80707
Create Date: 2026-10-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8d1f4a90808"
down_revision: Union[str, None] = "a7c0e3f80707"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_call_usages",
        sa.Column("id", sa.String(32), primary_key=True, comment="记录ID"),
        sa.Column("kind", sa.String(16), nullable=False, comment="调用类型"),
        sa.Column("model_id", sa.String(100), nullable=False, comment="模型ID"),
        sa.Column("model_name", sa.String(100), nullable=False, comment="模型名称"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0", comment="输入token"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0", comment="输出token"),
        sa.Column("search_calls", sa.Integer(), nullable=False, server_default="0", comment="联网次数"),
        sa.Column("inference_cost", sa.Numeric(12, 6), nullable=False, server_default="0", comment="推理费用(元)"),
        sa.Column("search_cost", sa.Numeric(12, 6), nullable=False, server_default="0", comment="联网费用(元)"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="调用时间"),
        sa.Column("created_by_id", sa.String(64), nullable=False, server_default="", comment="调用人ID"),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default="", comment="调用人"),
        comment="试发和多轮对话用量",
    )
    op.create_index("ix_ai_call_usages_created_at", "ai_call_usages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_call_usages_created_at", table_name="ai_call_usages")
    op.drop_table("ai_call_usages")
