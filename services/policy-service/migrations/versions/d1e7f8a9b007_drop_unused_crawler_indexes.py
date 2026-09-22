"""删掉爬虫监测里零命中的索引

`pg_stat_user_indexes` 实测：daily_stats 的 province_name 索引、tasks 的
province_name / site_name 索引 idx_scan 全是 0。页面按省份筛的是健康快照表，
任务基线表只被健康重算按 (site_code, tag) 关联，都不走这几个索引。
daily_stats 回填完约 175 万行，留着纯属白占空间并拖慢每次 upsert。

Revision ID: d1e7f8a9b007
Revises: c9d6e7f8a906
Create Date: 2026-09-22
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "d1e7f8a9b007"
down_revision: Union[str, None] = "c9d6e7f8a906"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

DROPPED = (
    ("ix_policy_crawler_daily_stats_province_name", "policy_crawler_daily_stats", ["province_name"]),
    ("ix_policy_crawler_tasks_province_name", "policy_crawler_tasks", ["province_name"]),
    ("ix_policy_crawler_tasks_site_name", "policy_crawler_tasks", ["site_name"]),
)


def upgrade() -> None:
    for name, table, _columns in DROPPED:
        op.drop_index(name, table_name=table)


def downgrade() -> None:
    for name, table, columns in DROPPED:
        op.create_index(name, table, columns)
