"""试发用量记「模板类型」，费用账单按一级业务板块（政策、客户、招投标）筛选

以前的试发没记是哪个模板，用户定的一律算政策。

Revision ID: c5e8a1b21515
Revises: b4d7f0a31414
Create Date: 2026-11-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c5e8a1b21515"
down_revision: Union[str, None] = "b4d7f0a31414"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_call_usages",
        sa.Column("prompt_category", sa.String(16), nullable=False, server_default="policy", comment="模板类型"),
    )


def downgrade() -> None:
    op.drop_column("ai_call_usages", "prompt_category")
