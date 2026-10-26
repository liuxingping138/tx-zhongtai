"""政策解读的一级行业、一级场景按码表名称精确筛选，补一级场景索引；政策类型按包含匹配，建三元组索引

Revision ID: d2e3f4a5b369
Revises: c1d2e3f4a258
Create Date: 2026-10-26
"""

from alembic import op

revision = "d2e3f4a5b369"
down_revision = "c1d2e3f4a258"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_policy_interpretations_scenario_l1_name", "policy_interpretations", ["scenario_l1_name"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_policy_base_tags_policy_types_trgm "
        "ON policy_base_tags USING gin (policy_types gin_trgm_ops)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_policy_base_tags_policy_types_trgm")
    op.drop_index("ix_policy_interpretations_scenario_l1_name", table_name="policy_interpretations")
