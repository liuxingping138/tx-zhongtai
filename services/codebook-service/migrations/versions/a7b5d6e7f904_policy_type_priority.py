"""政策类型加「优先级」：AI 给政策打类型时，多个类型同时命中按它排序

Revision ID: a7b5d6e7f904
Revises: f6a4c5d6e803
Create Date: 2026-10-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b5d6e7f904"
down_revision: Union[str, None] = "f6a4c5d6e803"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "codebook_policy_types",
        sa.Column("priority", sa.String(8), nullable=False, server_default="", comment="优先级"),
    )


def downgrade() -> None:
    op.drop_column("codebook_policy_types", "priority")
