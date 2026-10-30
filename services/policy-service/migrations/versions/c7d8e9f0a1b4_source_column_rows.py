"""信源按栏目展开：网站编码不再唯一，每行记对应的规则 ID，同步批次记新增了几行

规则表一行一个栏目，工作量按栏目算。从展开那天起，每条规则在信源表里一行，同一个网站的几行共用网站编码，
所以去掉网站编码的唯一约束（换成普通索引，按编码查还要快）；一条规则只展开成一行，规则 ID 加部分唯一索引。
信源表两万来行，建索引是瞬间的事，不用 CONCURRENTLY。

Revision ID: c7d8e9f0a1b4
Revises: b6c7d8e9f7a3
Create Date: 2026-10-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7d8e9f0a1b4"
down_revision: Union[str, None] = "b6c7d8e9f7a3"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "policy_sources",
        sa.Column("rule_id", sa.String(64), nullable=False, server_default="", comment="规则ID"),
    )
    op.drop_constraint("uq_policy_sources_site_code", "policy_sources", type_="unique")
    op.create_index("ix_policy_sources_site_code", "policy_sources", ["site_code"])
    op.create_index(
        "uq_policy_sources_rule_id",
        "policy_sources",
        ["rule_id"],
        unique=True,
        postgresql_where=sa.text("rule_id <> ''"),
    )
    op.add_column(
        "policy_crawler_config_syncs",
        sa.Column("added", sa.Integer(), nullable=False, server_default="0", comment="本次按栏目展开新增的信源行数"),
    )


def downgrade() -> None:
    # 已经展开出同编码的几行时恢复不了唯一约束：要先删掉展开的行（rule_id 不为空、不是原来那行的）。
    op.drop_column("policy_crawler_config_syncs", "added")
    op.drop_index("uq_policy_sources_rule_id", table_name="policy_sources")
    op.drop_index("ix_policy_sources_site_code", table_name="policy_sources")
    op.create_unique_constraint("uq_policy_sources_site_code", "policy_sources", ["site_code"])
    op.drop_column("policy_sources", "rule_id")
