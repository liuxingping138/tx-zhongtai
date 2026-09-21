"""add missing indexes for searchable text columns

model 里这三列写了 index=True，但初始迁移 d4e1f2a3b401 漏建了索引，
`alembic check` 一直报漂移。这三列正是筛选项预览与服务端搜索的查询列
（SELECT DISTINCT col WHERE col <> '' ORDER BY col LIMIT n），
没有索引就是全表顺序扫描 + 排序。

Revision ID: a7b4c5d6e704
Revises: f6a3b4c5d603
Create Date: 2026-09-21
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "a7b4c5d6e704"
down_revision: Union[str, None] = "f6a3b4c5d603"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

INDEXES = (
    ("ix_policy_base_tags_policy_name", "policy_base_tags", ["policy_name"]),
    ("ix_policy_base_tags_policy_types", "policy_base_tags", ["policy_types"]),
    ("ix_policy_interpretations_policy_title", "policy_interpretations", ["policy_title"]),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
