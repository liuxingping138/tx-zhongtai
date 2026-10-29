"""批量任务自动重跑三轮、删除不抹账单、token 列放宽到 bigint

Revision ID: e1a4c8d31111
Revises: d0f3b6c21010
Create Date: 2026-10-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1a4c8d31111"
down_revision: Union[str, None] = "d0f3b6c21010"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_batch_runs",
        sa.Column("retry_round", sa.Integer(), nullable=False, server_default="1", comment="当前轮次"),
    )
    op.add_column(
        "ai_batch_runs",
        sa.Column("round_rows", sa.Integer(), nullable=False, server_default="0", comment="本轮重问条数"),
    )
    op.add_column(
        "ai_batch_runs",
        sa.Column("round_starts_at", sa.DateTime(timezone=True), nullable=True, comment="本轮开始时间"),
    )
    op.add_column(
        "ai_batch_runs",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, comment="删除时间"),
    )
    for column, comment in (("input_tokens", "输入token"), ("output_tokens", "输出token")):
        op.alter_column(
            "ai_batch_runs",
            column,
            type_=sa.BigInteger(),
            existing_type=sa.Integer(),
            existing_nullable=False,
            existing_comment=comment,
        )


def downgrade() -> None:
    for column, comment in (("input_tokens", "输入token"), ("output_tokens", "输出token")):
        op.alter_column(
            "ai_batch_runs",
            column,
            type_=sa.Integer(),
            existing_type=sa.BigInteger(),
            existing_nullable=False,
            existing_comment=comment,
        )
    op.drop_column("ai_batch_runs", "deleted_at")
    op.drop_column("ai_batch_runs", "round_starts_at")
    op.drop_column("ai_batch_runs", "round_rows")
    op.drop_column("ai_batch_runs", "retry_round")
