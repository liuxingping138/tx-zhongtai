"""导出单独成档：READ 只能查看，EXPORT 可查看并导出，FULL 含写操作

现有授权保持原有能力：原来 READ 就能导出，所以在有导出动作的模块上把 READ 升为 EXPORT，
不让任何人因为这次拆分悄悄失去导出能力。之后需要「只能看不能导」的角色，由管理员改回 READ。

Revision ID: a8c4d2e3f702
Revises: f7b3c1d2e601
Create Date: 2026-09-23
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "a8c4d2e3f702"
down_revision: Union[str, None] = "f7b3c1d2e601"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE iam_role_grants g SET level = 'EXPORT'
        WHERE g.level = 'READ'
          AND EXISTS (SELECT 1 FROM iam_resource_actions a WHERE a.resource_id = g.resource_id AND a.action_code = 'export')
        """
    )
    # 动作门槛由 make seed 按目录同步；迁移里同步改掉，避免迁移后、seed 前导出对 EXPORT 角色误判。
    op.execute("UPDATE iam_resource_actions SET required_level = 'EXPORT' WHERE action_code = 'export'")


def downgrade() -> None:
    op.execute("UPDATE iam_resource_actions SET required_level = 'READ' WHERE action_code = 'export'")
    op.execute("UPDATE iam_role_grants SET level = 'READ' WHERE level = 'EXPORT'")
