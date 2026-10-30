"""记下类型判断问过、因为和已有基础标签内容相同而没写进去的源政策

读取进度往回调重扫时，「打过类型标的跳过」只认基础标签，认不出这些（各地转发的同一文件），每次都重新付费再问一遍。

Revision ID: f1a2b3c4d5e8
Revises: e9f0a1b2c3d6
Create Date: 2026-10-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e8"
down_revision: Union[str, None] = "e9f0a1b2c3d6"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policy_ai_skipped_sources",
        sa.Column("source_content_id", sa.String(200), primary_key=True, comment="源政策ID"),
        sa.Column("reason", sa.String(64), nullable=False, server_default="", comment="跳过原因"),
        sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=False, comment="跳过时间"),
        comment="政策AI打标跳过的源政策",
    )


def downgrade() -> None:
    op.drop_table("policy_ai_skipped_sources")
