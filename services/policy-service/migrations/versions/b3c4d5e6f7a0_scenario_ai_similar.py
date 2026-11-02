"""新增场景找相似：第四个打标任务，候选上记 AI 的判断

字面相似只找得出名称差不多的，意思近、说法不同的找不出来。让模型对照码表里同一个一级行业下的全部场景挑出最像的、
说是不是同一个场景，审核页的「系统建议」照它给。一个场景只问一次。
任务默认停用、没选模板，和另外三个打标任务一样在任务调度页设置后手动或定时执行。

Revision ID: b3c4d5e6f7a0
Revises: a2b3c4d5e6f9
Create Date: 2026-11-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3c4d5e6f7a0"
down_revision: Union[str, None] = "a2b3c4d5e6f9"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

JOB = "policy_ai_scenario"
JOB_TIME = "12:00"
CANDIDATE_COLUMNS = (
    sa.Column("ai_verdict", sa.String(16), nullable=False, server_default="", comment="AI判断"),
    sa.Column("ai_similar", sa.String(800), nullable=False, server_default="", comment="AI说最像的已有场景"),
    sa.Column("ai_target", sa.String(800), nullable=False, server_default="", comment="AI建议合并到"),
    sa.Column("ai_reason", sa.Text(), nullable=False, server_default="", comment="AI理由"),
    sa.Column("ai_checked_at", sa.DateTime(timezone=True), nullable=True, comment="AI判断时间"),
)
RUN_COLUMNS = (
    sa.Column("scenario_run_id", sa.String(32), nullable=False, server_default="", comment="找相似场景任务ID"),
    sa.Column("scenario_rows", sa.Integer(), nullable=False, server_default="0", comment="判断过的新增场景数"),
    sa.Column("scenario_failed", sa.Integer(), nullable=False, server_default="0", comment="找相似失败数"),
    sa.Column("scenario_cost", sa.Numeric(12, 6), nullable=False, server_default="0", comment="找相似场景费用(元)"),
)


def upgrade() -> None:
    for column in CANDIDATE_COLUMNS:
        op.add_column("policy_scenario_candidates", column.copy())
    for column in RUN_COLUMNS:
        op.add_column("policy_ai_runs", column.copy())
    # 一批默认看 200 个场景、每天最多花 20 元；没有正文，正文长度不起作用。
    op.execute("""
        INSERT INTO policy_ai_tasks(code, prompt_id, batch_size, content_max_chars, daily_cost_limit,
                                    cursor_date, cursor_content_id, version, updated_at, updated_by_name)
        SELECT 'scenario', '', 200, 0, 20, NULL, '', 1, NULL, ''
        WHERE NOT EXISTS (SELECT 1 FROM policy_ai_tasks WHERE code = 'scenario')
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
    op.execute("DELETE FROM policy_ai_tasks WHERE code = 'scenario'")
    for column in reversed(RUN_COLUMNS):
        op.drop_column("policy_ai_runs", column.name)
    for column in reversed(CANDIDATE_COLUMNS):
        op.drop_column("policy_scenario_candidates", column.name)
