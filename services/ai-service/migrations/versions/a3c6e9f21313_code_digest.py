"""模板和上线版本记下上传码表的内容摘要

上线检查原来只比码表文件名：业务人员按提示重传同名的「码表.txt」，算没改动，上线入口不出现，
按上线版本跑的批量任务和定时任务一直用旧码表。已有的行没有摘要（空串），重传一次就算改动，宁可多提示一次重新上线。

Revision ID: a3c6e9f21313
Revises: f2b5d9e41212
Create Date: 2026-10-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3c6e9f21313"
down_revision: Union[str, None] = "f2b5d9e41212"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

TABLES = ("ai_prompt_templates", "ai_template_releases")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("code_digest", sa.String(64), nullable=False, server_default="", comment="码表内容摘要"),
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "code_digest")
