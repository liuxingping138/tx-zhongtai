"""操作日志筛选项取候选值不再整表去重

「操作人」「动作」两个筛选项原来对没有索引的列做整表 DISTINCT，表只增不改（保留 180 天），越往后越慢。
这里给两列各建一个普通索引，查询改成沿索引逐个跳到下一个不同的值，步数只和不同值的个数有关。
「模块」用已有的 (module_code, action_code) 组合索引。

审计表一直有写入，建索引用 CONCURRENTLY，不锁写入；它不能在事务里跑，所以放在 autocommit_block 里。
中途失败时 CONCURRENTLY 会留下无效索引、alembic_version 也不前移，重跑时先删再建。
迁移由表的属主（审计服务的应用账号）执行，和建表的那次一样；建索引不需要已被收回的删改权。

Revision ID: e4b1c7d2a403
Revises: d3c9e8f1b302
Create Date: 2026-10-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "e4b1c7d2a403"
down_revision: Union[str, None] = "d3c9e8f1b302"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

# (索引名, 列, 中文说明)
INDEXES = (
    ("ix_audit_events_actor_name", "actor_name_snapshot", "操作人筛选项取候选值"),
    ("ix_audit_events_action_code", "action_code", "动作筛选项取候选值"),
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, column, comment in INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
            op.execute(f"CREATE INDEX CONCURRENTLY {name} ON audit_events ({column})")
            op.execute(f"COMMENT ON INDEX {name} IS '{comment}'")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, *_ in reversed(INDEXES):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
