"""爬虫监测 v2：只用采集总表，按「网站名称 + 省份 + 地市」统计。与 v1 的表并存。

Revision ID: a1b2c3d4e310
Revises: f3a9b0c1d209
Create Date: 2026-09-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e310"
down_revision: Union[str, None] = "f3a9b0c1d209"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policy_crawler_site_daily",
        sa.Column("collect_date", sa.Date(), nullable=False, comment="采集日期"),
        sa.Column("site_name", sa.String(255), nullable=False, comment="网站名称"),
        sa.Column("province_name", sa.String(64), nullable=False, comment="省份"),
        sa.Column("city_name", sa.String(64), nullable=False, comment="地市"),
        sa.Column("row_count", sa.Integer(), nullable=False, comment="数据条数"),
        sa.Column("last_created_at", sa.DateTime(timezone=True), nullable=True, comment="最新数据入库时间"),
        sa.Column("last_published_date", sa.Date(), nullable=True, comment="最近数据发布日期"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, comment="同步时间"),
        sa.PrimaryKeyConstraint("collect_date", "site_name", "province_name", "city_name"),
        comment="爬虫监测网站按天统计",
    )
    op.create_table(
        "policy_crawler_sites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, comment="主键"),
        sa.Column("site_name", sa.String(255), nullable=False, comment="网站名称"),
        sa.Column("province_name", sa.String(64), nullable=False, comment="省份"),
        sa.Column("city_name", sa.String(64), nullable=False, comment="地市"),
        sa.Column("total_rows", sa.BigInteger(), nullable=False, comment="数据总量"),
        sa.Column("last_created_at", sa.DateTime(timezone=True), nullable=True, comment="最新数据入库时间"),
        sa.Column("last_published_date", sa.Date(), nullable=True, comment="最近数据发布日期"),
        sa.Column("stale_days", sa.Integer(), nullable=True, comment="停更天数"),
        sa.Column("status", sa.String(16), nullable=False, comment="监测状态"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, comment="快照计算时间"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_name", "province_name", "city_name", name="uq_policy_crawler_sites_identity"),
        comment="爬虫监测网站快照",
    )
    op.create_table(
        "policy_crawler_v2_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, comment="主键"),
        sa.Column("mode", sa.String(16), nullable=False, comment="同步方式"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, comment="开始时间"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True, comment="结束时间"),
        sa.Column("date_from", sa.Date(), nullable=True, comment="重算起始采集日"),
        sa.Column("date_to", sa.Date(), nullable=True, comment="重算截止采集日"),
        sa.Column("days_synced", sa.Integer(), nullable=False, comment="重算天数"),
        sa.Column("site_rows", sa.Integer(), nullable=False, comment="网站快照行数"),
        sa.Column("status", sa.String(16), nullable=False, comment="批次状态"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="失败原因"),
        sa.Column("watermark", sa.DateTime(timezone=True), nullable=True, comment="已同步到的入库时间水位"),
        sa.PrimaryKeyConstraint("id"),
        comment="爬虫监测同步批次",
    )


def downgrade() -> None:
    op.drop_table("policy_crawler_v2_sync_runs")
    op.drop_table("policy_crawler_sites")
    op.drop_table("policy_crawler_site_daily")
