"""新增场景可以并到另一个待审场景

两个待审场景其实是同一个（换了说法）时，把一个并进另一个：行搬过去，以后 AI 再写被并入的说法也归到那个场景。

Revision ID: c4d5e6f7a8b1
Revises: b3c4d5e6f7a0
Create Date: 2026-11-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4d5e6f7a8b1"
down_revision: Union[str, None] = "b3c4d5e6f7a0"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "policy_scenario_candidates",
        sa.Column("merged_into", postgresql.UUID(as_uuid=True), nullable=True, comment="并入的新增场景ID"),
    )


def downgrade() -> None:
    op.drop_column("policy_scenario_candidates", "merged_into")
