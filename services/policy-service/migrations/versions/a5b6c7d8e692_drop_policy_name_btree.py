"""去掉基础标签政策名称、政策类型上没人用的 btree 索引

两列的筛选都是包含匹配，走的是 pg_trgm 的 GIN 索引；默认排序以省份编码打头，单列的名称索引也用不上。
btree 单条索引项有约 2704 字节的上限：标题或类型特别长（源库里有把整段脚本当标题的）时，这一行写不进去，
同一批打标、导入整批回滚。表已经有数据，删索引用 CONCURRENTLY，不锁写入。

Revision ID: a5b6c7d8e692
Revises: f4a5b6c7d581
Create Date: 2026-10-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "a5b6c7d8e692"
down_revision: Union[str, None] = "f4a5b6c7d581"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

INDEXES = (("ix_policy_base_tags_policy_name", "policy_name"), ("ix_policy_base_tags_policy_types", "policy_types"))


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _column in INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")


def downgrade() -> None:
    # 回退时库里已有超长的标题会建不上，这正是删它的原因：那种情况下先处理掉超长的行再回退。
    with op.get_context().autocommit_block():
        for name, column in INDEXES:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON policy_base_tags ({column})")
