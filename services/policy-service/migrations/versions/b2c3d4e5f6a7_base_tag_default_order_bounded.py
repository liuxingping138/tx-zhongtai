"""基础标签默认排序索引改成只取名称前 200 字：province_code, left(policy_name, 200), id

上一版（b1c2d3e4f5a6）直接在 policy_name（Text）上建 btree，把 a5b6c7d8e692 删掉的风险带了回来：
btree 单条索引项有约 2704 字节的上限，源库里有把整段脚本当标题的，这一行写不进去，同一批打标、导入整批回滚。
库里已经有超长标题时 CONCURRENTLY 建失败会留下 INVALID 索引：每次写入照样维护它，而 IF NOT EXISTS 让重跑跳过、永远修不好。
env.py 的会话级 lock_timeout = 5s 也带进 autocommit_block，CONCURRENTLY 等表上已有事务时 5 秒就失败，同样留下 INVALID 索引。

生产已经跑过 b1c2d3e4f5a6，所以不改它，另起这一步：先删（不管是有效还是 INVALID），关掉锁超时，再按表达式建。
名称前 200 个字最多 800 字节，加上省份编码和 ID 远在上限以内。列表 ORDER BY 用同一个表达式（models.default_order）。

Revision ID: b2c3d4e5f6a7
Revises: b1c2d3e4f5a6
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_policy_base_tags_default_order"
TABLE = "policy_base_tags"
# 和 models.BaseTag 上的同名 Index 一字不差（tests/test_default_order_index.py 核对）
COLUMNS = "province_code, left(policy_name, 200), id"


def _rebuild(columns: str) -> None:
    with op.get_context().autocommit_block():
        # CONCURRENTLY 要等表上已有的事务结束，不能被 env.py 的 5 秒锁超时打断。
        op.execute("SET lock_timeout = 0")
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX}")
        op.execute(f"CREATE INDEX CONCURRENTLY {INDEX} ON {TABLE} ({columns})")


def upgrade() -> None:
    _rebuild(COLUMNS)


def downgrade() -> None:
    # 回到上一版的整列索引：库里已有超长标题时会建不上，这正是这一步要修的问题，先处理掉超长的行再回退。
    _rebuild("province_code, policy_name, id")
