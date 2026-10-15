"""AI 打表初始表：提示词模板、批量提问任务、执行进程心跳、出站事件

Revision ID: a1c4e7f20101
Revises:
Create Date: 2026-10-15
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1c4e7f20101"
down_revision: Union[str, None] = None
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_prompt_templates",
        sa.Column("id", sa.String(32), primary_key=True, comment="模板ID"),
        sa.Column("title", sa.String(255), nullable=False, comment="提示词标题"),
        sa.Column("content", sa.Text(), nullable=False, comment="提示词内容"),
        sa.Column("output_fields", sa.Text(), nullable=False, server_default="", comment="新增输出字段"),
        sa.Column("model_id", sa.String(100), nullable=False, server_default="", comment="模型ID"),
        sa.Column("excel_name", sa.String(255), nullable=False, server_default="", comment="Excel 文件名"),
        sa.Column("excel_rows", sa.Integer(), nullable=False, server_default="0", comment="Excel 数据行数"),
        sa.Column(
            "excel_headers", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb"), comment="Excel 表头"
        ),
        sa.Column("code_name", sa.String(255), nullable=False, server_default="", comment="码表文件名"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1", comment="版本号"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="创建时间"),
        sa.Column("created_by_id", sa.String(64), nullable=False, server_default="", comment="创建人ID"),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default="", comment="创建人"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="更新时间"),
        sa.Column("updated_by_id", sa.String(64), nullable=False, server_default="", comment="更新人ID"),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default="", comment="更新人"),
        comment="提示词模板",
    )
    op.create_table(
        "ai_batch_runs",
        sa.Column("id", sa.String(32), primary_key=True, comment="任务ID"),
        sa.Column("prompt_id", sa.String(32), nullable=False, comment="模板ID"),
        sa.Column("prompt_title", sa.String(255), nullable=False, comment="提问标题"),
        sa.Column("prompt_content", sa.Text(), nullable=False, server_default="", comment="提问模板内容"),
        sa.Column("output_fields", sa.Text(), nullable=False, server_default="", comment="解析字段快照"),
        sa.Column("model_id", sa.String(100), nullable=False, comment="模型ID"),
        sa.Column("model_name", sa.String(100), nullable=False, comment="模型名称"),
        sa.Column("thinking", sa.Boolean(), nullable=False, server_default=sa.false(), comment="深度思考"),
        sa.Column("row_limit", sa.Integer(), nullable=False, server_default="0", comment="运行条数上限"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued", comment="运行状态"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0", comment="总条数"),
        sa.Column("done_count", sa.Integer(), nullable=False, server_default="0", comment="已处理条数"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0", comment="失败条数"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0", comment="输入token"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0", comment="输出token"),
        sa.Column("search_calls", sa.Integer(), nullable=False, server_default="0", comment="联网次数"),
        sa.Column("inference_cost", sa.Numeric(12, 6), nullable=False, server_default="0", comment="推理费用(元)"),
        sa.Column("search_cost", sa.Numeric(12, 6), nullable=False, server_default="0", comment="联网费用(元)"),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false(), comment="请求停止"),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True, comment="心跳时间"),
        sa.Column("error_message", sa.Text(), nullable=False, server_default="", comment="错误信息"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True, comment="开始时间"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True, comment="结束时间"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="发起时间"),
        sa.Column("created_by_id", sa.String(64), nullable=False, server_default="", comment="发起人ID"),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default="", comment="发起人"),
        comment="批量提问任务",
    )
    op.create_index("ix_ai_batch_runs_prompt_id", "ai_batch_runs", ["prompt_id"])
    op.create_index("ix_ai_batch_runs_status", "ai_batch_runs", ["status"])
    op.create_index("ix_ai_batch_runs_created_at", "ai_batch_runs", ["created_at"])
    op.create_table(
        "ai_worker_heartbeat",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False, comment="主键"),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False, comment="最近心跳时间"),
        comment="批量执行进程心跳",
    )
    op.create_table(
        "ai_outbox",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True, comment="事件ID"),
        sa.Column("event_type", sa.String(128), nullable=False, comment="事件类型"),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1", comment="事件结构版本"),
        sa.Column("payload", postgresql.JSONB(), nullable=False, comment="事件内容"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending", comment="投递状态"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0", comment="重试次数"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True, comment="下次重试时间"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="创建时间"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="失败原因"),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True, comment="租约截止时间"),
        comment="AI 打表服务出站事件",
    )
    op.create_index("ix_ai_outbox_status", "ai_outbox", ["status"])
    op.create_index("ix_ai_outbox_next_retry_at", "ai_outbox", ["next_retry_at"])


def downgrade() -> None:
    op.drop_table("ai_outbox")
    op.drop_table("ai_worker_heartbeat")
    op.drop_table("ai_batch_runs")
    op.drop_table("ai_prompt_templates")
