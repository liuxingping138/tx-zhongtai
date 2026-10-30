"""批量任务费用流水：重跑花的钱记在实际花钱那天

Revision ID: f2b5d9e41212
Revises: e1a4c8d31111
Create Date: 2026-10-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b5d9e41212"
down_revision: Union[str, None] = "e1a4c8d31111"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_run_costs",
        sa.Column("run_id", sa.String(32), primary_key=True, comment="任务ID"),
        sa.Column("day", sa.Date(), primary_key=True, comment="花费日期（北京）"),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0", comment="输入token"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0", comment="输出token"),
        sa.Column("search_calls", sa.Integer(), nullable=False, server_default="0", comment="联网次数"),
        sa.Column("inference_cost", sa.Numeric(12, 6), nullable=False, server_default="0", comment="推理费用(元)"),
        sa.Column("search_cost", sa.Numeric(12, 6), nullable=False, server_default="0", comment="联网费用(元)"),
        comment="批量任务费用流水",
    )
    op.create_index("ix_ai_run_costs_day", "ai_run_costs", ["day"])
    # 已有任务的钱没法再拆到哪天花的，整笔记在发起那天，和原来账单上的数一致。
    op.execute(
        """
        INSERT INTO ai_run_costs
            (run_id, day, input_tokens, output_tokens, search_calls, inference_cost, search_cost)
        SELECT id, (created_at AT TIME ZONE 'Asia/Shanghai')::date,
               input_tokens, output_tokens, search_calls, inference_cost, search_cost
        FROM ai_batch_runs
        WHERE input_tokens > 0 OR output_tokens > 0 OR search_calls > 0
           OR inference_cost > 0 OR search_cost > 0
        """
    )


def downgrade() -> None:
    op.drop_index("ix_ai_run_costs_day", table_name="ai_run_costs")
    op.drop_table("ai_run_costs")
