"""任务调度配置、执行队列和心跳。"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "c3d4e5f6a512"
down_revision = "b2c3d4e5f411"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("policy_scheduled_jobs",
        sa.Column("code", sa.String(40), primary_key=True, comment="任务编码"),
        sa.Column("enabled", sa.Boolean(), nullable=False, comment="是否启用每日计划"),
        sa.Column("daily_time", sa.String(5), nullable=False, comment="北京时间每日执行时刻"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False, comment="下次计划时间"),
        sa.Column("version", sa.Integer(), nullable=False, comment="配置版本"),
        comment="定时同步任务配置")
    op.create_table("policy_scheduled_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, comment="执行编号"),
        sa.Column("job_code", sa.String(40), sa.ForeignKey("policy_scheduled_jobs.code"), nullable=False, comment="任务编码"),
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
        sa.Column("result", postgresql.JSONB(), comment="同步结果摘要"), comment="定时同步执行记录")
    op.create_index("uq_scheduled_run_active", "policy_scheduled_runs", ["job_code"], unique=True,
                    postgresql_where=sa.text("status IN ('queued', 'running', 'retrying')"))
    op.create_index("ix_scheduled_run_history", "policy_scheduled_runs", ["job_code", "created_at"])
    op.create_table("policy_scheduler_heartbeat",
        sa.Column("id", sa.Integer(), primary_key=True, comment="固定记录编号"),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False, comment="最近心跳时间"), comment="调度进程心跳")
    # 首次上线安排在下一次每日时刻；以后重启沿用持久化的到期时间。
    op.execute("""INSERT INTO policy_scheduled_jobs(code, enabled, daily_time, next_run_at, version)
        SELECT code, true, clock,
          ((now() AT TIME ZONE 'Asia/Shanghai')::date + clock::time +
           CASE WHEN (now() AT TIME ZONE 'Asia/Shanghai')::time >= clock::time
                THEN interval '1 day' ELSE interval '0 day' END) AT TIME ZONE 'Asia/Shanghai', 1
        FROM (VALUES ('crawler-v1', '10:00'), ('crawler-v2', '10:10')) AS jobs(code, clock)""")


def downgrade():
    op.drop_table("policy_scheduler_heartbeat")
    op.drop_table("policy_scheduled_runs")
    op.drop_table("policy_scheduled_jobs")
