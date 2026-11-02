"""行业场景码表加「补充状态」：采纳进来的新增场景让 AI 补描述、人确认

新增场景采纳进码表时只有名称和编码，描述全空。AI 补好描述后标「待确认」，业务人员核对后标「已确认」。
原有的行为空。不进 Excel 导入列和内容哈希。

Revision ID: c9d8e9f0a107
Revises: b8c7d8e9f006
Create Date: 2026-11-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d8e9f0a107"
down_revision: Union[str, None] = "b8c7d8e9f006"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "codebook_scenarios",
        sa.Column("enrich_status", sa.String(16), nullable=False, server_default="", comment="补充状态"),
    )
    # 已经同步进来、描述还空着的新增场景，排进补描述
    op.execute("UPDATE codebook_scenarios SET enrich_status = '待补充' WHERE is_new_scenario = '是' AND desc_90 = ''")


def downgrade() -> None:
    op.drop_column("codebook_scenarios", "enrich_status")
