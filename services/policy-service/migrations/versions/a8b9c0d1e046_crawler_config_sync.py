"""爬虫配置同步：按规则表把信源标成已爬，记批次；调度新增任务 crawler_config，默认每天 18:00

Revision ID: a8b9c0d1e046
Revises: f7a8b9c0d035
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a8b9c0d1e046"
down_revision = "f7a8b9c0d035"
branch_labels = None
depends_on = None

_JOB = "crawler_config"
# 爬虫同事周五下午更新规则表，傍晚跑能赶上当天；更早要看就在周报页手动同步。
_DAILY_TIME = "18:00"


def upgrade():
    op.create_table(
        "policy_crawler_config_syncs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, comment="批次编号"),
        sa.Column("status", sa.String(16), nullable=False, comment="状态"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, comment="开始时间"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True, comment="结束时间"),
        sa.Column("rule_rows", sa.Integer(), nullable=False, server_default="0", comment="规则表栏目行数"),
        sa.Column("rule_codes", sa.Integer(), nullable=False, server_default="0", comment="规则表网站编码数"),
        sa.Column(
            "blank_code_rows", sa.Integer(), nullable=False, server_default="0", comment="规则表没填网站编码的行数"
        ),
        sa.Column("matched", sa.Integer(), nullable=False, server_default="0", comment="关联上的信源数"),
        sa.Column("marked", sa.Integer(), nullable=False, server_default="0", comment="本次标为已爬的信源数"),
        sa.Column(
            "unknown_codes", sa.Integer(), nullable=False, server_default="0", comment="信源表里没有的网站编码数"
        ),
        sa.Column("error_message", sa.Text(), nullable=True, comment="失败原因"),
        comment="爬虫配置同步批次",
    )
    op.create_index("ix_policy_crawler_config_syncs_started_at", "policy_crawler_config_syncs", ["started_at"])
    op.execute(f"""
        INSERT INTO policy_scheduled_jobs(code, enabled, daily_time, next_run_at, version)
        SELECT '{_JOB}', true, '{_DAILY_TIME}',
               CASE WHEN (now() AT TIME ZONE 'Asia/Shanghai')::time < time '{_DAILY_TIME}'
                    THEN (now() AT TIME ZONE 'Asia/Shanghai')::date + time '{_DAILY_TIME}'
                    ELSE (now() AT TIME ZONE 'Asia/Shanghai')::date + time '{_DAILY_TIME}' + interval '1 day'
               END AT TIME ZONE 'Asia/Shanghai',
               1
        WHERE NOT EXISTS (SELECT 1 FROM policy_scheduled_jobs WHERE code = '{_JOB}')
    """)


def downgrade():
    op.execute(f"DELETE FROM policy_scheduled_runs WHERE job_code = '{_JOB}'")
    op.execute(f"DELETE FROM policy_scheduled_jobs WHERE code = '{_JOB}'")
    op.drop_index("ix_policy_crawler_config_syncs_started_at", table_name="policy_crawler_config_syncs")
    op.drop_table("policy_crawler_config_syncs")
