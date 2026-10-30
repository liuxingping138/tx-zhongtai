"""爬虫配置同步批次记下没展开的规则：改了网站编码的、栏目名和已有信源撞号的、同一网页已在另一编码下的

原来这几种只写日志，调度页只看得到「新增多少行」，本周配置数比规则表少时查不到原因。

Revision ID: e9f0a1b2c3d6
Revises: d8e9f0a1b2c5
Create Date: 2026-10-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e9f0a1b2c3d6"
down_revision: Union[str, None] = "d8e9f0a1b2c5"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

COLUMNS = (
    ("moved", "展开后改了网站编码的规则数"),
    ("conflicts", "栏目名和已有信源重复没展开的规则数"),
    ("duplicates", "同一网页已在另一网站编码下没展开的规则数"),
)


def upgrade() -> None:
    for name, comment in COLUMNS:
        op.add_column(
            "policy_crawler_config_syncs",
            sa.Column(name, sa.Integer(), nullable=False, server_default="0", comment=comment),
        )


def downgrade() -> None:
    for name, _comment in COLUMNS:
        op.drop_column("policy_crawler_config_syncs", name)
