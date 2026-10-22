"""批量任务记录发起来源、上线版本号、服务档位和费用上限：政策服务定时打标用上线版本、低优档跑，到上限自动停

Revision ID: a7c0e3f80707
Revises: f6b9d2e70606
Create Date: 2026-10-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c0e3f80707"
down_revision: Union[str, None] = "f6b9d2e70606"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_batch_runs",
        sa.Column("source", sa.String(16), nullable=False, server_default="manual", comment="发起来源"),
    )
    op.add_column("ai_batch_runs", sa.Column("release_no", sa.Integer(), nullable=True, comment="上线版本号"))
    op.add_column(
        "ai_batch_runs",
        sa.Column("service_tier", sa.String(16), nullable=False, server_default="", comment="服务档位"),
    )
    op.add_column(
        "ai_batch_runs", sa.Column("cost_limit", sa.Numeric(12, 6), nullable=True, comment="费用上限(元)")
    )


def downgrade() -> None:
    for column in ("cost_limit", "service_tier", "release_no", "source"):
        op.drop_column("ai_batch_runs", column)
