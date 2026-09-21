"""add chinese table and column comments

Revision ID: e5f3b4c5d702
Revises: d4e2a3b4c601
Create Date: 2026-09-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from platform_common.orm_base import Base
from app.domain import models as _models  # noqa: F401

revision: str = "e5f3b4c5d702"
down_revision: Union[str, None] = "d4e2a3b4c601"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def _literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def _apply(clear: bool = False) -> None:
    for table in Base.metadata.sorted_tables:
        table_comment = None if clear else table.comment
        op.execute(sa.text(f"COMMENT ON TABLE {table.name} IS {_literal(table_comment)}"))
        for column in table.columns:
            comment = None if clear else column.comment
            op.execute(sa.text(f"COMMENT ON COLUMN {table.name}.{column.name} IS {_literal(comment)}"))


def upgrade() -> None:
    _apply()


def downgrade() -> None:
    _apply(clear=True)
