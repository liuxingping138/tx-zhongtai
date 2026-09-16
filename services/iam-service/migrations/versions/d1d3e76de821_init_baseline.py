"""init baseline

Revision ID: d1d3e76de821
Revises: 
Create Date: 2026-09-16 16:51:50.047660

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1d3e76de821'
down_revision: Union[str, None] = None
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
