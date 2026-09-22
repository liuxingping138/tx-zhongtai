"""同步批次记录入库时间水位

固定天数窗口会漏掉滞后入库的数据（实测最大滞后 4 天，且没有保证上限）。
改为记录水位后，用入库时间找出被动过的采集日再整天重算，不再依赖窗口猜测。

Revision ID: c9d6e7f8a906
Revises: b8c5d6e7f805
Create Date: 2026-09-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d6e7f8a906"
down_revision: Union[str, None] = "b8c5d6e7f805"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "policy_crawler_sync_runs",
        sa.Column("watermark", sa.DateTime(timezone=True), nullable=True, comment="已同步到的入库时间水位"),
    )


def downgrade() -> None:
    op.drop_column("policy_crawler_sync_runs", "watermark")
