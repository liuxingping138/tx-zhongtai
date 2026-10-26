"""政策名称、政策原文名称改成输入关键词模糊查找：建 pg_trgm 三元组索引，几百万条时 ILIKE '%关键词%' 也走索引

Revision ID: c1d2e3f4a258
Revises: b9c0d1e2f147
Create Date: 2026-10-26
"""

from alembic import op

revision = "c1d2e3f4a258"
down_revision = "b9c0d1e2f147"
branch_labels = None
depends_on = None


def upgrade():
    # pg_trgm 是可信扩展，库的属主就能建，不需要超级用户。
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_policy_base_tags_policy_name_trgm "
        "ON policy_base_tags USING gin (policy_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_policy_interpretations_policy_title_trgm "
        "ON policy_interpretations USING gin (policy_title gin_trgm_ops)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_policy_interpretations_policy_title_trgm")
    op.execute("DROP INDEX IF EXISTS ix_policy_base_tags_policy_name_trgm")
