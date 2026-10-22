"""模板可选系统码表；新增模板上线版本，定时任务只跑上线时冻结的那一版

Revision ID: f6b9d2e70606
Revises: e5a8c1d60505
Create Date: 2026-10-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6b9d2e70606"
down_revision: Union[str, None] = "e5a8c1d60505"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_prompt_templates",
        sa.Column("code_table", sa.String(32), nullable=False, server_default="", comment="系统码表"),
    )
    op.add_column(
        "ai_prompt_templates",
        sa.Column("release_id", sa.String(32), nullable=True, comment="当前上线版本ID"),
    )
    op.create_table(
        "ai_template_releases",
        sa.Column("id", sa.String(32), primary_key=True, comment="版本ID"),
        sa.Column("prompt_id", sa.String(32), nullable=False, comment="模板ID"),
        sa.Column("release_no", sa.Integer(), nullable=False, comment="上线版本号"),
        sa.Column("title", sa.String(255), nullable=False, comment="提示词标题"),
        sa.Column("category", sa.String(16), nullable=False, comment="模板类型"),
        sa.Column("content", sa.Text(), nullable=False, comment="提示词内容"),
        sa.Column("output_fields", sa.Text(), nullable=False, comment="新增输出字段"),
        sa.Column("model_id", sa.String(100), nullable=False, comment="模型ID"),
        sa.Column("code_table", sa.String(32), nullable=False, server_default="", comment="系统码表"),
        sa.Column("code_name", sa.String(255), nullable=False, server_default="", comment="码表文件名"),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=False, comment="上线时间"),
        sa.Column("released_by_id", sa.String(64), nullable=False, server_default="", comment="上线人ID"),
        sa.Column("released_by_name", sa.String(128), nullable=False, server_default="", comment="上线人"),
        comment="模板上线版本",
    )
    op.create_index("ix_ai_template_releases_prompt_id", "ai_template_releases", ["prompt_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_template_releases_prompt_id", table_name="ai_template_releases")
    op.drop_table("ai_template_releases")
    op.drop_column("ai_prompt_templates", "release_id")
    op.drop_column("ai_prompt_templates", "code_table")
