"""爬虫监测去掉 v2：同步批次表改名，调度任务编码 crawler-v2 改为 crawler，执行历史一起迁过去

Revision ID: c4e7a2d9f318
Revises: b1d2e3f4a816
"""

from alembic import op

revision = "c4e7a2d9f318"
down_revision = "b1d2e3f4a816"
branch_labels = None
depends_on = None


def _rename_job(old: str, new: str) -> None:
    # 执行记录外键指向任务编码且不级联：先插新任务，再改记录，最后删旧任务。
    op.execute(
        f"""INSERT INTO policy_scheduled_jobs(code, enabled, daily_time, next_run_at, version)
        SELECT '{new}', enabled, daily_time, next_run_at, version FROM policy_scheduled_jobs WHERE code = '{old}'
        ON CONFLICT (code) DO NOTHING"""
    )
    op.execute(f"UPDATE policy_scheduled_runs SET job_code = '{new}' WHERE job_code = '{old}'")
    op.execute(f"DELETE FROM policy_scheduled_jobs WHERE code = '{old}'")


def upgrade() -> None:
    op.rename_table("policy_crawler_v2_sync_runs", "policy_crawler_sync_runs")
    op.execute("ALTER INDEX policy_crawler_v2_sync_runs_pkey RENAME TO policy_crawler_sync_runs_pkey")
    _rename_job("crawler-v2", "crawler")


def downgrade() -> None:
    _rename_job("crawler", "crawler-v2")
    op.execute("ALTER INDEX policy_crawler_sync_runs_pkey RENAME TO policy_crawler_v2_sync_runs_pkey")
    op.rename_table("policy_crawler_sync_runs", "policy_crawler_v2_sync_runs")
