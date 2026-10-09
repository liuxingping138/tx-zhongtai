"""去掉用户「归档」状态，现有归档账号并入禁用

归档与禁用的效果完全相同（都不能登录、都会下线会话），只是名字不同，留着只会让管理员困惑。
降级不还原：迁移后无法区分哪些账号原本是归档。

Revision ID: d5f2b7c40e11
Revises: c4e8a1b92d10
Create Date: 2026-10-09
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "d5f2b7c40e11"
down_revision: Union[str, None] = "c4e8a1b92d10"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE iam_users SET status = 'disabled', version = version + 1, updated_at = now() "
        "WHERE status = 'archived'"
    )


def downgrade() -> None:
    pass
