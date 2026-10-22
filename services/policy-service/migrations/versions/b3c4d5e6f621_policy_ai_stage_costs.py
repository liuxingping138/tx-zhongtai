"""政策 AI 打标批次按步骤记费用（类型判断、政策解读、市场机会），账单能拆到每一步

Revision ID: b3c4d5e6f621
Revises: a2b3c4d5e520
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from alembic import op

revision = "b3c4d5e6f621"
down_revision = "a2b3c4d5e520"
branch_labels = None
depends_on = None

_COLUMNS = (("type_cost", "类型判断费用(元)"), ("interpret_cost", "政策解读费用(元)"), ("opportunity_cost", "市场机会费用(元)"))


def upgrade():
    for name, comment in _COLUMNS:
        op.add_column(
            "policy_ai_runs",
            sa.Column(name, sa.Numeric(12, 6), nullable=False, server_default="0", comment=comment),
        )


def downgrade():
    for name, _ in _COLUMNS:
        op.drop_column("policy_ai_runs", name)
