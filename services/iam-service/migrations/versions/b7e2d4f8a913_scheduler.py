"""任务调度：配置、执行队列和心跳三张表，登记每天清理失效会话

原来清理只能手动跑 make iam-session-cleanup，没人跑就一直涨。登记后默认启用，每天北京时间 03:30。
表结构与公共调度引擎（platform_common.scheduler.models）一致，这里冻结成字面量，不 import 运行时模型。

Revision ID: b7e2d4f8a913
Revises: a3d6f9b1c720
Create Date: 2026-10-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7e2d4f8a913"
down_revision: Union[str, None] = "a3d6f9b1c720"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

JOB = "iam_session_cleanup"
DAILY_TIME = "03:30"


def upgrade() -> None:
    op.create_table(
        "iam_scheduled_jobs",
        sa.Column("code", sa.String(40), primary_key=True, comment="任务编码"),
        sa.Column("enabled", sa.Boolean(), nullable=False, comment="是否启用每日计划"),
        sa.Column("daily_time", sa.String(5), nullable=False, comment="北京时间每日执行时刻"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False, comment="下次计划时间"),
        sa.Column("version", sa.Integer(), nullable=False, comment="配置版本"),
        comment="定时任务配置",
    )
    op.create_table(
        "iam_scheduled_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, comment="执行编号"),
        sa.Column(
            "job_code", sa.String(40), sa.ForeignKey("iam_scheduled_jobs.code"), nullable=False, comment="任务编码"
        ),
        sa.Column("trigger", sa.String(16), nullable=False, comment="触发方式"),
        sa.Column("actor_name", sa.String(255), nullable=False, comment="发起人"),
        sa.Column("status", sa.String(16), nullable=False, comment="执行状态"),
        sa.Column("attempts", sa.Integer(), nullable=False, comment="已尝试次数"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="入队时间"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False, comment="原计划时间"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, comment="可执行或重试时间"),
        sa.Column("started_at", sa.DateTime(timezone=True), comment="首次开始时间"),
        sa.Column("finished_at", sa.DateTime(timezone=True), comment="结束时间"),
        sa.Column("sync_run_id", postgresql.UUID(as_uuid=True), comment="当前同步批次编号"),
        sa.Column("error_message", sa.Text(), comment="最近一次失败原因"),
        sa.Column("result", postgresql.JSONB(), comment="同步结果摘要"),
        comment="定时任务执行记录",
    )
    op.create_index(
        "uq_scheduled_run_active",
        "iam_scheduled_runs",
        ["job_code"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running', 'retrying')"),
    )
    op.create_index("ix_scheduled_run_history", "iam_scheduled_runs", ["job_code", "created_at"])
    op.create_table(
        "iam_scheduler_heartbeat",
        sa.Column("id", sa.Integer(), primary_key=True, comment="固定记录编号"),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False, comment="最近心跳时间"),
        comment="调度进程心跳",
    )
    # 首次上线排在下一个 03:30；以后重启沿用持久化的到期时间。
    op.execute(f"""
        INSERT INTO iam_scheduled_jobs(code, enabled, daily_time, next_run_at, version)
        SELECT '{JOB}', true, '{DAILY_TIME}',
               CASE WHEN (now() AT TIME ZONE 'Asia/Shanghai')::time < time '{DAILY_TIME}'
                    THEN (now() AT TIME ZONE 'Asia/Shanghai')::date + time '{DAILY_TIME}'
                    ELSE (now() AT TIME ZONE 'Asia/Shanghai')::date + time '{DAILY_TIME}' + interval '1 day'
               END AT TIME ZONE 'Asia/Shanghai',
               1
    """)


def downgrade() -> None:
    op.drop_table("iam_scheduler_heartbeat")
    op.drop_table("iam_scheduled_runs")
    op.drop_table("iam_scheduled_jobs")
