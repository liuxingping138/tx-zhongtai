"""widen source data_type

Revision ID: e5f2a3b4c502
Revises: d4e1f2a3b401
Create Date: 2026-09-18

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f2a3b4c502"
down_revision: Union[str, None] = "d4e1f2a3b401"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "policy_sources",
        "data_type",
        existing_type=sa.String(255),
        type_=sa.Text(),
        existing_nullable=False,
        existing_server_default="",
    )


def downgrade() -> None:
    op.alter_column(
        "policy_sources",
        "data_type",
        existing_type=sa.Text(),
        type_=sa.String(255),
        existing_nullable=False,
        existing_server_default="",
    )
