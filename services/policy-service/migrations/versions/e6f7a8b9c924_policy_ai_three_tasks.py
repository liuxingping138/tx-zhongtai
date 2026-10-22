"""政策 AI 打标拆成三个任务（类型判断、政策解读、市场机会），各有模板、每批条数、正文长度和每日上限，在任务调度里各自定时和执行

Revision ID: e6f7a8b9c924
Revises: d5e6f7a8b823
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from alembic import op

revision = "e6f7a8b9c924"
down_revision = "d5e6f7a8b823"
branch_labels = None
depends_on = None

# 新增的两个调度任务默认停用，时刻和类型判断错开。
_NEW_JOBS = (("policy_ai_interpret", "11:00"), ("policy_ai_opportunity", "11:30"))


def _next_daily(daily_time: str) -> str:
    return (
        f"((now() AT TIME ZONE 'Asia/Shanghai')::date + time '{daily_time}' + interval '1 day') "
        "AT TIME ZONE 'Asia/Shanghai'"
    )


def upgrade():
    op.create_table(
        "policy_ai_tasks",
        sa.Column("code", sa.String(16), primary_key=True, comment="任务编码"),
        sa.Column("prompt_id", sa.String(32), nullable=False, server_default="", comment="使用的上线模板ID"),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="1000", comment="每批条数"),
        sa.Column(
            "content_max_chars", sa.Integer(), nullable=False, server_default="0", comment="正文截取字数（0 为全文）"
        ),
        sa.Column(
            "daily_cost_limit", sa.Numeric(12, 2), nullable=False, server_default="100", comment="每日费用上限(元)"
        ),
        sa.Column("cursor_date", sa.Date(), nullable=True, comment="读取进度：采集日期（类型判断用）"),
        sa.Column(
            "cursor_content_id", sa.String(200), nullable=False, server_default="", comment="读取进度：该日已读到的正文ID"
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1", comment="版本号"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, comment="更新时间"),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default="", comment="操作人"),
        comment="政策AI打标任务",
    )
    # 原来一份设置三步共用：模板各归各的，条数、正文长度、每日上限三个任务先沿用原值，读取进度归类型判断。
    op.execute("""
        INSERT INTO policy_ai_tasks(code, prompt_id, batch_size, content_max_chars, daily_cost_limit,
                                    cursor_date, cursor_content_id, updated_at, updated_by_name)
        SELECT 'type', type_prompt_id, batch_size, content_max_chars, daily_cost_limit,
               cursor_date, cursor_content_id, updated_at, updated_by_name FROM policy_ai_config
        UNION ALL
        SELECT 'interpret', interpret_prompt_id, batch_size, content_max_chars, daily_cost_limit,
               NULL, '', updated_at, updated_by_name FROM policy_ai_config
        UNION ALL
        SELECT 'opportunity', opportunity_prompt_id, batch_size, content_max_chars, daily_cost_limit,
               NULL, '', updated_at, updated_by_name FROM policy_ai_config
    """)
    op.drop_table("policy_ai_config")

    op.add_column(
        "policy_ai_runs",
        sa.Column("task", sa.String(16), nullable=False, server_default="type", comment="任务编码"),
    )
    op.add_column(
        "policy_ai_runs",
        sa.Column("opportunity_rows", sa.Integer(), nullable=False, server_default="0", comment="回填市场机会行数"),
    )
    op.add_column(
        "policy_ai_runs",
        sa.Column("opportunity_failed", sa.Integer(), nullable=False, server_default="0", comment="市场机会失败条数"),
    )
    op.execute("COMMENT ON COLUMN policy_ai_runs.source_rows IS '本批处理的政策条数'")
    op.create_index("ix_policy_ai_runs_task_started_at", "policy_ai_runs", ["task", "started_at"])

    # 调度：原「政策 AI 打标」就是类型判断（它负责读源库），改名保留计划和执行记录；另加两个任务。
    op.execute("""
        INSERT INTO policy_scheduled_jobs(code, enabled, daily_time, next_run_at, version)
        SELECT 'policy_ai_type', enabled, daily_time, next_run_at, version FROM policy_scheduled_jobs
        WHERE code = 'policy_ai'
    """)
    op.execute("UPDATE policy_scheduled_runs SET job_code = 'policy_ai_type' WHERE job_code = 'policy_ai'")
    op.execute("DELETE FROM policy_scheduled_jobs WHERE code = 'policy_ai'")
    for code, daily_time in _NEW_JOBS:
        op.execute(f"""
            INSERT INTO policy_scheduled_jobs(code, enabled, daily_time, next_run_at, version)
            SELECT '{code}', false, '{daily_time}', {_next_daily(daily_time)}, 1
            WHERE NOT EXISTS (SELECT 1 FROM policy_scheduled_jobs WHERE code = '{code}')
        """)


def downgrade():
    for code, _ in _NEW_JOBS:
        op.execute(f"DELETE FROM policy_scheduled_runs WHERE job_code = '{code}'")
        op.execute(f"DELETE FROM policy_scheduled_jobs WHERE code = '{code}'")
    op.execute("""
        INSERT INTO policy_scheduled_jobs(code, enabled, daily_time, next_run_at, version)
        SELECT 'policy_ai', enabled, daily_time, next_run_at, version FROM policy_scheduled_jobs
        WHERE code = 'policy_ai_type'
    """)
    op.execute("UPDATE policy_scheduled_runs SET job_code = 'policy_ai' WHERE job_code = 'policy_ai_type'")
    op.execute("DELETE FROM policy_scheduled_jobs WHERE code = 'policy_ai_type'")

    op.drop_index("ix_policy_ai_runs_task_started_at", table_name="policy_ai_runs")
    op.execute("COMMENT ON COLUMN policy_ai_runs.source_rows IS '读取条数'")
    op.drop_column("policy_ai_runs", "opportunity_failed")
    op.drop_column("policy_ai_runs", "opportunity_rows")
    op.drop_column("policy_ai_runs", "task")

    op.create_table(
        "policy_ai_config",
        sa.Column("id", sa.Integer(), primary_key=True, comment="固定记录编号"),
        sa.Column("type_prompt_id", sa.String(32), nullable=False, server_default="", comment="政策类型判断模板ID"),
        sa.Column("interpret_prompt_id", sa.String(32), nullable=False, server_default="", comment="政策解读模板ID"),
        sa.Column(
            "opportunity_prompt_id", sa.String(32), nullable=False, server_default="", comment="政策市场机会模板ID"
        ),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="1000", comment="每批打标条数"),
        sa.Column(
            "content_max_chars", sa.Integer(), nullable=False, server_default="0", comment="正文截取字数（0 为全文）"
        ),
        sa.Column(
            "daily_cost_limit", sa.Numeric(12, 2), nullable=False, server_default="100", comment="每日费用上限(元)"
        ),
        sa.Column("cursor_date", sa.Date(), nullable=False, comment="读取进度：采集日期"),
        sa.Column(
            "cursor_content_id", sa.String(200), nullable=False, server_default="", comment="读取进度：该日已读到的正文ID"
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1", comment="版本号"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, comment="更新时间"),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default="", comment="操作人"),
        comment="政策AI打标配置",
    )
    op.execute("""
        INSERT INTO policy_ai_config(id, type_prompt_id, interpret_prompt_id, opportunity_prompt_id, batch_size,
                                     content_max_chars, daily_cost_limit, cursor_date, cursor_content_id)
        SELECT 1, t.prompt_id, i.prompt_id, o.prompt_id, t.batch_size, t.content_max_chars, t.daily_cost_limit,
               COALESCE(t.cursor_date, (now() AT TIME ZONE 'Asia/Shanghai')::date), t.cursor_content_id
        FROM policy_ai_tasks t, policy_ai_tasks i, policy_ai_tasks o
        WHERE t.code = 'type' AND i.code = 'interpret' AND o.code = 'opportunity'
    """)
    op.drop_table("policy_ai_tasks")
