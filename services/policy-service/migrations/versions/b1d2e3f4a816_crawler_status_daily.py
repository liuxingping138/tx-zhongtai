"""爬虫监测每日状态分布：卡片「较上周」对比的依据。数据由同步写入和补齐，迁移只建表。

Revision ID: b1d2e3f4a816
Revises: a9c1e3f5b712
"""

import sqlalchemy as sa
from alembic import op

revision = "b1d2e3f4a816"
down_revision = "a9c1e3f5b712"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_crawler_status_daily",
        sa.Column("snapshot_date", sa.Date(), primary_key=True, comment="统计日期"),
        sa.Column("sites", sa.Integer(), nullable=False, comment="网站总数"),
        sa.Column("normal", sa.Integer(), nullable=False, comment="正常网站数"),
        sa.Column("watch", sa.Integer(), nullable=False, comment="关注网站数"),
        sa.Column("stale", sa.Integer(), nullable=False, comment="停更网站数"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, comment="计算时间"),
        comment="爬虫监测每日状态分布",
    )


def downgrade() -> None:
    op.drop_table("policy_crawler_status_daily")
