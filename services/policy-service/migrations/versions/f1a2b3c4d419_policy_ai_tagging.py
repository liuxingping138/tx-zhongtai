"""政策 AI 打标：配置表、批次表；基础标签记源政策ID和打标时间；任务调度加「政策 AI 打标」，默认不启用

Revision ID: f1a2b3c4d419
Revises: e9f0a1b2c318
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f1a2b3c4d419"
down_revision = "e9f0a1b2c318"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "policy_ai_config",
        sa.Column("id", sa.Integer(), primary_key=True, comment="固定记录编号"),
        sa.Column("type_prompt_id", sa.String(32), nullable=False, server_default="", comment="政策类型判断模板ID"),
        sa.Column("interpret_prompt_id", sa.String(32), nullable=False, server_default="", comment="政策解读模板ID"),
        sa.Column(
            "opportunity_prompt_id", sa.String(32), nullable=False, server_default="", comment="政策市场机会模板ID"
        ),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="1000", comment="每批打标条数"),
        sa.Column("content_max_chars", sa.Integer(), nullable=False, server_default="15000", comment="正文截取字数"),
        sa.Column(
            "daily_cost_limit", sa.Numeric(12, 2), nullable=False, server_default="100", comment="每日费用上限(元)"
        ),
        sa.Column("cursor_date", sa.Date(), nullable=False, comment="读取进度：采集日期"),
        sa.Column("cursor_content_id", sa.String(200), nullable=False, server_default="", comment="读取进度：该日已读到的正文ID"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1", comment="版本号"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, comment="更新时间"),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default="", comment="操作人"),
        comment="政策AI打标配置",
    )
    # 默认从上线当天的采集数据读起；要补历史在任务调度页把起始日期往前调。
    op.execute(
        "INSERT INTO policy_ai_config(id, cursor_date) VALUES (1, (now() AT TIME ZONE 'Asia/Shanghai')::date)"
    )
    op.create_table(
        "policy_ai_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, comment="批次编号"),
        sa.Column("status", sa.String(16), nullable=False, comment="状态"),
        sa.Column("stage", sa.String(16), nullable=False, comment="进行到的步骤"),
        sa.Column("source_from", sa.String(240), nullable=False, server_default="", comment="读取起点"),
        sa.Column("source_to", sa.String(240), nullable=False, server_default="", comment="读取终点"),
        sa.Column("source_rows", sa.Integer(), nullable=False, server_default="0", comment="读取条数"),
        sa.Column("type_run_id", sa.String(32), nullable=False, server_default="", comment="类型判断任务ID"),
        sa.Column("tagged_rows", sa.Integer(), nullable=False, server_default="0", comment="写入基础标签条数"),
        sa.Column("type_failed", sa.Integer(), nullable=False, server_default="0", comment="类型判断失败条数"),
        sa.Column("interpret_run_id", sa.String(32), nullable=False, server_default="", comment="政策解读任务ID"),
        sa.Column("opportunity_run_id", sa.String(32), nullable=False, server_default="", comment="市场机会任务ID"),
        sa.Column("interpret_rows", sa.Integer(), nullable=False, server_default="0", comment="写入政策解读条数"),
        sa.Column("interpret_failed", sa.Integer(), nullable=False, server_default="0", comment="解读失败条数"),
        sa.Column("cost", sa.Numeric(12, 6), nullable=False, server_default="0", comment="费用(元)"),
        sa.Column("note", sa.Text(), nullable=False, server_default="", comment="说明"),
        sa.Column("error_message", sa.Text(), nullable=False, server_default="", comment="失败原因"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, comment="开始时间"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True, comment="结束时间"),
        comment="政策AI打标批次",
    )
    op.create_index("ix_policy_ai_runs_started_at", "policy_ai_runs", ["started_at"])
    op.add_column("policy_base_tags", sa.Column("source_content_id", sa.String(200), nullable=True, comment="源政策ID"))
    op.add_column(
        "policy_base_tags", sa.Column("tagged_at", sa.DateTime(timezone=True), nullable=True, comment="AI打标时间")
    )
    op.create_unique_constraint("uq_policy_base_tags_source_content_id", "policy_base_tags", ["source_content_id"])
    # 上线时默认不启用：先在页面手动执行几批确认效果，再打开每日计划。
    op.execute("""INSERT INTO policy_scheduled_jobs(code, enabled, daily_time, next_run_at, version)
        SELECT 'policy_ai', false, '02:00',
          ((now() AT TIME ZONE 'Asia/Shanghai')::date + time '02:00' + interval '1 day') AT TIME ZONE 'Asia/Shanghai', 1
        WHERE NOT EXISTS (SELECT 1 FROM policy_scheduled_jobs WHERE code = 'policy_ai')""")


def downgrade():
    op.execute("DELETE FROM policy_scheduled_runs WHERE job_code = 'policy_ai'")
    op.execute("DELETE FROM policy_scheduled_jobs WHERE code = 'policy_ai'")
    op.drop_constraint("uq_policy_base_tags_source_content_id", "policy_base_tags", type_="unique")
    op.drop_column("policy_base_tags", "tagged_at")
    op.drop_column("policy_base_tags", "source_content_id")
    op.drop_index("ix_policy_ai_runs_started_at", table_name="policy_ai_runs")
    op.drop_table("policy_ai_runs")
    op.drop_table("policy_ai_config")
