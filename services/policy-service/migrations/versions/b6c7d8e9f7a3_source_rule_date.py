"""信源记下爬虫配置同步见过的最早规则日期

上线时间「只往前挪、不往后挪」是为了最早的规则被删后网站不换周；可导入时直接标已爬、上线时间随手填成
2024-10-01 的网站，今天才建规则，也被这条挡住、没算进本周。记下同步见过的最早规则日期，就分得清：
第一次见到规则时早晚都对齐，见过之后才只往前挪。

已有的行留空：下一次同步第一次见到它们的规则时对齐（这条规则上线前同步一直是早晚都对齐的，结果一样）。

Revision ID: b6c7d8e9f7a3
Revises: a5b6c7d8e692
Create Date: 2026-10-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6c7d8e9f7a3"
down_revision: Union[str, None] = "a5b6c7d8e692"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "policy_sources",
        sa.Column("rule_date", sa.String(10), nullable=False, server_default="", comment="规则最早创建日期"),
    )


def downgrade() -> None:
    op.drop_column("policy_sources", "rule_date")
