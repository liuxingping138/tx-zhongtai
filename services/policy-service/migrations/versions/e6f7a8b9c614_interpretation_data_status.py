"""政策解读新增数据状态（待验证 / 人工验证）。

存量行统一回填为「待验证」，由人工核对后改为「人工验证」。
"""

import sqlalchemy as sa
from alembic import op

revision = "e6f7a8b9c614"
down_revision = "c3d4e5f6a512"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "policy_interpretations",
        sa.Column(
            "data_status",
            sa.String(16),
            nullable=False,
            server_default="待验证",
            comment="数据状态",
        ),
    )


def downgrade():
    op.drop_column("policy_interpretations", "data_status")
