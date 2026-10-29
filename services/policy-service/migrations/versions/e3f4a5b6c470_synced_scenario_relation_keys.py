"""已同步进码表的新增场景，关联主键换成编码形式

同步新增场景原来只回填编码、不重算关联主键，这些行的主键还是「政策 + 新:六级名称 + 机会类型」。
之后导入或重新解读按编码算出的主键对不上，会再插一条重复的。这里把它们换成「政策 + 行业场景编码 + 机会类型」；
换完会和已有的行撞上的（两行讲的是同一件事）不动，留给人核对。

Revision ID: e3f4a5b6c470
Revises: d2e3f4a5b369
Create Date: 2026-10-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "e3f4a5b6c470"
down_revision: Union[str, None] = "d2e3f4a5b369"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        WITH candidates AS (
            SELECT id, policy_uid || industry_scenario_code || opportunity_type AS target
            FROM policy_interpretations
            WHERE industry_scenario_code <> '' AND position('新:' IN relation_key) > 0
        ),
        alone AS (
            SELECT c.id, c.target
            FROM candidates c
            WHERE (SELECT count(*) FROM candidates d WHERE d.target = c.target) = 1
              AND NOT EXISTS (SELECT 1 FROM policy_interpretations o WHERE o.relation_key = c.target)
        )
        UPDATE policy_interpretations t
        SET relation_key = alone.target
        FROM alone
        WHERE t.id = alone.id
        """
    )


def downgrade() -> None:
    # 旧主键是从六级名称拼出来的，换掉后不再需要；回退时不改回去。
    pass
