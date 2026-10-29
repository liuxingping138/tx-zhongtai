"""模板上线只留管理档：查看档没有任何功能用，勾了让人误以为有用

Revision ID: e3b7c2d9f114
Revises: d8f1a6c3e905
Create Date: 2026-10-29
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "e3b7c2d9f114"
down_revision: Union[str, None] = "d8f1a6c3e905"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

_RELEASES = "(SELECT id FROM iam_resources WHERE code = 'ai.releases')"


def upgrade() -> None:
    # 同步资源清单只增改不删动作，查看动作要在这里删掉；原来只给了查看档的授权本来就不起作用，一并清掉。
    op.execute(f"DELETE FROM iam_resource_actions WHERE resource_id = {_RELEASES} AND action_code = 'list'")
    op.execute(f"DELETE FROM iam_role_grants WHERE resource_id = {_RELEASES} AND level <> 'FULL'")
    op.execute(f"DELETE FROM iam_user_grants WHERE resource_id = {_RELEASES} AND level <> 'FULL'")


def downgrade() -> None:
    # 查看动作由 make seed 按旧清单补回；清掉的授权本来不起作用，不恢复。
    pass
