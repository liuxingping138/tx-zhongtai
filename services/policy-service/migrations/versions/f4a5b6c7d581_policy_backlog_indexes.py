"""打标待办、筛选项和「待同步」条数只读部分索引，不再整表扫描

任务调度页开着时每 5 秒数一次三个打标任务的待办，解读列表每次打开都数一遍待同步的新增场景，
基础标签的「是否穿透」「是否解读」筛选项要去重：几百万行时每次都整表扫一遍（本机 200 万行模拟：
待办计数 0.55 秒、待同步计数 1.5 秒）。这里只给待办的行建部分索引（几十 KB），去重的两列建普通索引。

表已经有数据，建索引用 CONCURRENTLY，不锁写入；它不能在事务里跑，所以放在 autocommit_block 里。
中途失败时 CONCURRENTLY 会留下无效索引、alembic_version 也不前移，重跑时先删再建。
索引的条件写死在这里，不引用运行时的模型：以后模型改了，这一步迁移照样能在空库里从头跑通。

Revision ID: f4a5b6c7d581
Revises: e3f4a5b6c470
Create Date: 2026-10-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "f4a5b6c7d581"
down_revision: Union[str, None] = "e3f4a5b6c470"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

# (索引名, 表, 列, 部分索引条件, 中文说明)
INDEXES = (
    (
        "ix_policy_base_tags_interpret_backlog",
        "policy_base_tags",
        "tagged_at, id",
        "need_interpret = '是' AND source_content_id IS NOT NULL AND interpreted_at IS NULL",
        "政策解读待办：需要解读、还没解读的 AI 打标行",
    ),
    (
        "ix_policy_base_tags_opportunity_backlog",
        "policy_base_tags",
        "interpreted_at, id",
        "interpreted_at IS NOT NULL AND opportunity_at IS NULL",
        "市场机会待办：解读过、还没补市场机会",
    ),
    (
        "ix_policy_base_tags_need_interpret",
        "policy_base_tags",
        "need_interpret",
        "",
        "是否解读筛选项去重",
    ),
    (
        "ix_policy_base_tags_is_penetrate",
        "policy_base_tags",
        "is_penetrate",
        "is_penetrate <> ''",
        "是否穿透筛选项去重（只含填了的行）",
    ),
    (
        "ix_policy_interpretations_unsynced_scenarios",
        "policy_interpretations",
        "updated_at, id",
        "is_new_scenario = '是' AND data_status = '人工验证' AND scenario_synced_at IS NULL",
        "人工验证过、还没同步进码表的新增场景",
    ),
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, columns, where, comment in INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
            predicate = f" WHERE {where}" if where else ""
            op.execute(f"CREATE INDEX CONCURRENTLY {name} ON {table} ({columns}){predicate}")
            op.execute(f"COMMENT ON INDEX {name} IS '{comment}'")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, *_ in reversed(INDEXES):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
