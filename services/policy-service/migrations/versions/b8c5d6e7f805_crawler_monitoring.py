"""爬虫监测：任务基线、按天采集统计、健康快照、同步批次

数据来自爬虫库（MySQL）按天聚合后的结果，页面只查这几张表，不回查 400 万行的原始表。

Revision ID: b8c5d6e7f805
Revises: a7b4c5d6e704
Create Date: 2026-09-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c5d6e7f805"
down_revision: Union[str, None] = "a7b4c5d6e704"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policy_crawler_tasks",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False, comment="主键"),
        sa.Column("correlation", sa.String(64), nullable=False, comment="爬虫规则唯一ID"),
        sa.Column("site_code", sa.String(100), nullable=False, server_default="", comment="网站编码"),
        sa.Column("site_name", sa.String(255), nullable=False, server_default="", comment="网站名称"),
        sa.Column("province_name", sa.String(64), nullable=False, server_default="", comment="省份名称"),
        sa.Column("city_name", sa.String(64), nullable=False, server_default="", comment="地市名称"),
        sa.Column("tag", sa.String(255), nullable=False, server_default="", comment="标签"),
        sa.Column("source_url", sa.Text(), nullable=False, server_default="", comment="栏目源链接"),
        sa.Column("rule_state", sa.Integer(), nullable=False, server_default="0", comment="爬虫规则状态"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, comment="同步时间"),
        sa.UniqueConstraint("correlation", name="uq_policy_crawler_tasks_correlation"),
        comment="政策爬虫任务基线",
    )
    op.create_index("ix_policy_crawler_tasks_site_code", "policy_crawler_tasks", ["site_code"])
    op.create_index("ix_policy_crawler_tasks_site_name", "policy_crawler_tasks", ["site_name"])
    op.create_index("ix_policy_crawler_tasks_province_name", "policy_crawler_tasks", ["province_name"])

    op.create_table(
        "policy_crawler_daily_stats",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False, comment="主键"),
        sa.Column("collect_date", sa.Date(), nullable=False, comment="采集日期"),
        sa.Column("site_code", sa.String(100), nullable=False, server_default="", comment="网站编码"),
        sa.Column("site_name", sa.String(255), nullable=False, server_default="", comment="网站名称"),
        sa.Column("province_name", sa.String(64), nullable=False, server_default="", comment="省份名称"),
        sa.Column("city_name", sa.String(64), nullable=False, server_default="", comment="地市名称"),
        sa.Column("tag", sa.String(255), nullable=False, server_default="", comment="标签"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0", comment="采集条数"),
        sa.Column("named_count", sa.Integer(), nullable=False, server_default="0", comment="有政策名称条数"),
        sa.Column("content_count", sa.Integer(), nullable=False, server_default="0", comment="有正文条数"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, comment="同步时间"),
        sa.UniqueConstraint("collect_date", "site_code", "tag", name="uq_policy_crawler_daily_stats_key"),
        comment="政策爬虫按天采集统计",
    )
    op.create_index("ix_policy_crawler_daily_stats_collect_date", "policy_crawler_daily_stats", ["collect_date"])
    op.create_index("ix_policy_crawler_daily_stats_site_code", "policy_crawler_daily_stats", ["site_code"])
    op.create_index("ix_policy_crawler_daily_stats_province_name", "policy_crawler_daily_stats", ["province_name"])

    op.create_table(
        "policy_crawler_task_health",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False, comment="主键"),
        sa.Column("site_code", sa.String(100), nullable=False, server_default="", comment="网站编码"),
        sa.Column("site_name", sa.String(255), nullable=False, server_default="", comment="网站名称"),
        sa.Column("province_name", sa.String(64), nullable=False, server_default="", comment="省份名称"),
        sa.Column("city_name", sa.String(64), nullable=False, server_default="", comment="地市名称"),
        sa.Column("tag", sa.String(255), nullable=False, server_default="", comment="标签"),
        sa.Column("source_url", sa.Text(), nullable=False, server_default="", comment="栏目源链接"),
        sa.Column("last_collect_date", sa.Date(), nullable=True, comment="最后采集日期"),
        sa.Column("stale_days", sa.Integer(), nullable=True, comment="停更天数"),
        sa.Column("count_7d", sa.Integer(), nullable=False, server_default="0", comment="近7天采集条数"),
        sa.Column("count_30d", sa.Integer(), nullable=False, server_default="0", comment="近30天采集条数"),
        sa.Column("count_90d", sa.Integer(), nullable=False, server_default="0", comment="近90天采集条数"),
        sa.Column("count_total", sa.Integer(), nullable=False, server_default="0", comment="统计窗口内累计条数"),
        sa.Column("health_status", sa.String(16), nullable=False, comment="健康状态"),
        sa.Column("in_rules", sa.Boolean(), nullable=False, server_default=sa.false(), comment="爬虫规则表是否仍有配置"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, comment="快照计算时间"),
        sa.UniqueConstraint("site_code", "tag", name="uq_policy_crawler_task_health_key"),
        comment="政策爬虫任务健康快照",
    )
    op.create_index("ix_policy_crawler_task_health_site_code", "policy_crawler_task_health", ["site_code"])
    op.create_index("ix_policy_crawler_task_health_site_name", "policy_crawler_task_health", ["site_name"])
    op.create_index("ix_policy_crawler_task_health_province_name", "policy_crawler_task_health", ["province_name"])
    op.create_index("ix_policy_crawler_task_health_health_status", "policy_crawler_task_health", ["health_status"])
    op.create_index("ix_policy_crawler_task_health_stale_days", "policy_crawler_task_health", ["stale_days"])

    op.create_table(
        "policy_crawler_sync_runs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, nullable=False, comment="主键"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, comment="开始时间"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True, comment="结束时间"),
        sa.Column("date_from", sa.Date(), nullable=False, comment="同步起始日期"),
        sa.Column("date_to", sa.Date(), nullable=False, comment="同步截止日期"),
        sa.Column("task_rows", sa.Integer(), nullable=False, server_default="0", comment="同步任务基线行数"),
        sa.Column("stat_rows", sa.Integer(), nullable=False, server_default="0", comment="写入按天统计行数"),
        sa.Column("health_rows", sa.Integer(), nullable=False, server_default="0", comment="重算健康快照行数"),
        sa.Column("status", sa.String(16), nullable=False, server_default="running", comment="批次状态"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="失败原因"),
        comment="政策爬虫同步批次",
    )


def downgrade() -> None:
    op.drop_table("policy_crawler_sync_runs")
    op.drop_table("policy_crawler_task_health")
    op.drop_table("policy_crawler_daily_stats")
    op.drop_table("policy_crawler_tasks")
