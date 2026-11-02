"""新增场景补描述：第五个打标任务

采纳进码表的新场景只有名称，描述全空。让模型照同级场景的写法写描述，写回码表标「待确认」，人核对后确认。
任务默认停用、没选模板，和其他打标任务一样在任务调度页设置后执行。

Revision ID: d5e6f7a8b9c2
Revises: c4d5e6f7a8b1
Create Date: 2026-11-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c2"
down_revision: Union[str, None] = "c4d5e6f7a8b1"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

JOB = "policy_ai_enrich"
JOB_TIME = "12:30"
RUN_COLUMNS = (
    sa.Column("enrich_run_id", sa.String(32), nullable=False, server_default="", comment="补描述任务ID"),
    sa.Column("enrich_rows", sa.Integer(), nullable=False, server_default="0", comment="补好描述的新增场景数"),
    sa.Column("enrich_failed", sa.Integer(), nullable=False, server_default="0", comment="补描述失败数"),
    sa.Column("enrich_cost", sa.Numeric(12, 6), nullable=False, server_default="0", comment="补描述费用(元)"),
)


def upgrade() -> None:
    for column in RUN_COLUMNS:
        op.add_column("policy_ai_runs", column.copy())
    op.execute("""
        INSERT INTO policy_ai_tasks(code, prompt_id, batch_size, content_max_chars, daily_cost_limit,
                                    cursor_date, cursor_content_id, version, updated_at, updated_by_name)
        SELECT 'enrich', '', 200, 0, 20, NULL, '', 1, NULL, ''
        WHERE NOT EXISTS (SELECT 1 FROM policy_ai_tasks WHERE code = 'enrich')
    """)
    op.execute(f"""
        INSERT INTO policy_scheduled_jobs(code, enabled, daily_time, next_run_at, version)
        SELECT '{JOB}', false, '{JOB_TIME}',
               ((now() AT TIME ZONE 'Asia/Shanghai')::date + time '{JOB_TIME}' + interval '1 day')
               AT TIME ZONE 'Asia/Shanghai', 1
        WHERE NOT EXISTS (SELECT 1 FROM policy_scheduled_jobs WHERE code = '{JOB}')
    """)


def downgrade() -> None:
    op.execute(f"DELETE FROM policy_scheduled_runs WHERE job_code = '{JOB}'")
    op.execute(f"DELETE FROM policy_scheduled_jobs WHERE code = '{JOB}'")
    op.execute("DELETE FROM policy_ai_tasks WHERE code = 'enrich'")
    for column in reversed(RUN_COLUMNS):
        op.drop_column("policy_ai_runs", column.name)
