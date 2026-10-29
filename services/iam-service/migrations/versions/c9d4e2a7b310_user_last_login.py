"""用户加最近登录时间和 IP，按已有会话回填

Revision ID: c9d4e2a7b310
Revises: b7e2d4f8a913
Create Date: 2026-10-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d4e2a7b310"
down_revision: Union[str, None] = "b7e2d4f8a913"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "iam_users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True, comment="最近登录时间"),
    )
    op.add_column(
        "iam_users",
        sa.Column("last_login_ip", sa.String(length=64), nullable=False, server_default="", comment="最近登录IP"),
    )
    # 会话表里每次登录都留了一行（清理任务只删失效后又过了保留天数的），取每人最近一次；很久没登录的回填不到，留空。
    op.execute(
        """
        UPDATE iam_users AS u
        SET last_login_at = s.created_at, last_login_ip = COALESCE(s.ip, '')
        FROM (
            SELECT DISTINCT ON (user_id) user_id, created_at, LEFT(client_info->>'ip', 64) AS ip
            FROM iam_sessions
            ORDER BY user_id, created_at DESC
        ) AS s
        WHERE s.user_id = u.id
        """
    )


def downgrade() -> None:
    op.drop_column("iam_users", "last_login_ip")
    op.drop_column("iam_users", "last_login_at")
