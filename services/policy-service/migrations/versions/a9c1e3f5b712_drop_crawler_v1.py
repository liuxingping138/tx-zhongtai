"""下线爬虫监测旧版：删除任务口径的四张表和它的定时任务。

Revision ID: a9c1e3f5b712
Revises: e6f7a8b9c614
"""

from alembic import op

revision = "a9c1e3f5b712"
down_revision = "e6f7a8b9c614"
branch_labels = None
depends_on = None

V1_TABLES = (
    "policy_crawler_task_health",
    "policy_crawler_daily_stats",
    "policy_crawler_tasks",
    "policy_crawler_sync_runs",
)


def upgrade() -> None:
    # 执行记录通过外键指向任务，先删记录再删任务。
    op.execute("DELETE FROM policy_scheduled_runs WHERE job_code = 'crawler-v1'")
    op.execute("DELETE FROM policy_scheduled_jobs WHERE code = 'crawler-v1'")
    for table in V1_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")


def downgrade() -> None:
    raise NotImplementedError("旧版爬虫监测的表和数据已删除，不支持回退；需要时从备份恢复")
