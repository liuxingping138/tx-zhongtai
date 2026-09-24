"""出站事件加租约：投递途中进程重启时，delivering 事件到期后可被重新认领。

Revision ID: b2c3d4e5f411
Revises: a1b2c3d4e310
Create Date: 2026-09-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f411"
down_revision: Union[str, None] = "a1b2c3d4e310"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "policy_outbox",
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True, comment="租约截止时间"),
    )


def downgrade() -> None:
    op.drop_column("policy_outbox", "lease_until")
