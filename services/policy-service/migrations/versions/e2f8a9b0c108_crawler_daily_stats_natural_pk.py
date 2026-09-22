"""把按天采集统计的主键换成天然联合键

派生事实表，同步按 (collect_date, site_code, tag) 覆盖写，没有任何代码按 id 引用。
UUID 主键索引 idx_scan 一直是 0，回填到约 175 万行时白占约 67MB，还拖慢每次 upsert。

Revision ID: e2f8a9b0c108
Revises: d1e7f8a9b007
Create Date: 2026-09-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f8a9b0c108"
down_revision: Union[str, None] = "d1e7f8a9b007"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

TABLE = "policy_crawler_daily_stats"
NATURAL_KEY = ["collect_date", "site_code", "tag"]


def upgrade() -> None:
    op.drop_constraint(f"{TABLE}_pkey", TABLE, type_="primary")
    op.drop_column(TABLE, "id")
    op.drop_constraint("uq_policy_crawler_daily_stats_key", TABLE, type_="unique")
    op.create_primary_key(f"{TABLE}_pkey", TABLE, NATURAL_KEY)


def downgrade() -> None:
    op.drop_constraint(f"{TABLE}_pkey", TABLE, type_="primary")
    op.create_unique_constraint("uq_policy_crawler_daily_stats_key", TABLE, NATURAL_KEY)
    op.add_column(TABLE, sa.Column("id", sa.Uuid(), nullable=True, comment="主键"))
    op.execute(f"UPDATE {TABLE} SET id = gen_random_uuid() WHERE id IS NULL")  # noqa: S608
    op.alter_column(TABLE, "id", nullable=False)
    op.create_primary_key(f"{TABLE}_pkey", TABLE, ["id"])
