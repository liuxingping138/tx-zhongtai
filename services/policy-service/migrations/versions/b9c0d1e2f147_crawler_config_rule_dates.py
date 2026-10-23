"""爬虫配置同步改按规则创建日期记上线时间：批次表记「对齐上线时间」的条数

Revision ID: b9c0d1e2f147
Revises: a8b9c0d1e046
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "b9c0d1e2f147"
down_revision = "a8b9c0d1e046"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "policy_crawler_config_syncs",
        sa.Column(
            "redated",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="已爬但上线时间对齐成规则创建日期的信源数",
        ),
    )


def downgrade():
    op.drop_column("policy_crawler_config_syncs", "redated")
