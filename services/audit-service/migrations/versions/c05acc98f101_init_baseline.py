"""init baseline

Revision ID: c05acc98f101
Revises: 
Create Date: 2026-09-16 16:55:33.416858

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c05acc98f101'
down_revision: Union[str, None] = None
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
