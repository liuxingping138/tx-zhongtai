"""信源新增网站类型、爬虫状态、上线时间

Revision ID: e9f0a1b2c318
Revises: d8e9f0a1b217
"""

import sqlalchemy as sa
from alembic import op

revision = "e9f0a1b2c318"
down_revision = "d8e9f0a1b217"
branch_labels = None
depends_on = None

COLUMNS = (
    ("site_type", 255, "网站类型"),
    ("crawler_status", 64, "爬虫状态"),
    ("online_date", 10, "上线时间"),
)


def upgrade() -> None:
    for name, length, comment in COLUMNS:
        op.add_column(
            "policy_sources",
            sa.Column(name, sa.String(length), nullable=False, server_default="", comment=comment),
        )


def downgrade() -> None:
    for name, _, _ in COLUMNS:
        op.drop_column("policy_sources", name)
