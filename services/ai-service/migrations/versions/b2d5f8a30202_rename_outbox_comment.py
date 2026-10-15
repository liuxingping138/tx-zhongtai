"""模块改名为「AI提问」，出站事件表的中文注释跟着改

Revision ID: b2d5f8a30202
Revises: a1c4e7f20101
Create Date: 2026-10-15
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "b2d5f8a30202"
down_revision: Union[str, None] = "a1c4e7f20101"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table_comment("ai_outbox", "AI提问服务出站事件", existing_comment="AI 打表服务出站事件")


def downgrade() -> None:
    op.create_table_comment("ai_outbox", "AI 打表服务出站事件", existing_comment="AI提问服务出站事件")
