"""统一按网站名称关联数据；保留旧聚合并标记待回填。

Revision ID: f3a9b0c1d209
Revises: e2f8a9b0c108
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f3a9b0c1d209"
down_revision = "e2f8a9b0c108"
branch_labels = None
depends_on = None

TABLES = ("policy_crawler_tasks", "policy_crawler_daily_stats", "policy_crawler_task_health")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("site_key", sa.String(128), nullable=True, comment="网站内部关联键"))
        if table == "policy_crawler_tasks":
            expression = "CASE WHEN trim(site_name) <> '' THEN 'name:' || md5(trim(site_name)) ELSE 'code:' || trim(site_code) END"
        else:
            # 旧缓存按编码聚合，空编码可能包含多个网站；保留旧分组，但不能猜测新的归属。
            expression = "'legacy:' || md5(site_code)"
        op.execute(sa.text(f"UPDATE {table} SET site_key = {expression}"))
        op.alter_column(table, "site_key", nullable=False)
    daily = TABLES[1]
    op.add_column(daily, sa.Column("identity_verified", sa.Boolean(), nullable=False,
                                 server_default=sa.true(), comment="网站关联是否已校验"))
    # 历史空编码聚合已经丢失网站边界，不能靠迁移猜回来。原数据保留，重新按日同步后替换。
    op.execute(sa.text(f"UPDATE {daily} SET identity_verified = false"))
    op.alter_column(daily, "identity_verified", server_default=None)
    op.drop_constraint(f"{daily}_pkey", daily, type_="primary")
    op.create_primary_key(f"{daily}_pkey", daily, ["collect_date", "site_key", "tag"])
    # 旧 PyMySQL 返回的北京时间被当成 UTC 存入，统一成真实 UTC 时间点。
    op.execute("UPDATE policy_crawler_sync_runs SET watermark = watermark - interval '8 hours' WHERE watermark IS NOT NULL")
    health = TABLES[2]
    op.drop_constraint("uq_policy_crawler_task_health_key", health, type_="unique")
    op.create_unique_constraint("uq_policy_crawler_task_health_key", health, ["site_key", "tag"])


def downgrade() -> None:
    # 新模型允许同一个空编码/标签有多个网站，回退会合并并丢失身份；拒绝静默降级。
    raise RuntimeError("网站身份迁移不能无损回退，请恢复迁移前备份。")
