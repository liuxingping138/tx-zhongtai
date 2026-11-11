"""操作日志加「业务线」（政策 / 客户 / 招投标），可按类型筛选

以后由审计服务入库时算好（app.domain.business_lines）。这里给已有记录补上：
政策、客户、招投标模块的事件按模块编码第一段补；AI提问的事件按事件内容里记的模板类型补（只有 2026-11-11 之后的事件记了）。
更早的 AI 事件要按目标ID 去 ai 库查模板类型，跨库，迁移里不做：用一次性的
deploy/compose/scripts/backfill-audit-business-line.sh 补。

补的只是分类标签，谁、何时、做了什么都不动。审计迁移由超级用户执行（make SERVER=1 migrate-audit），应用账号仍然只有查和插。
建索引用 CONCURRENTLY（审计表一直有写入），不能在事务里跑，放在 autocommit_block 里。

Revision ID: a6d4e0f5c705
Revises: f5c3d9e4b604
Create Date: 2026-11-11
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a6d4e0f5c705"
down_revision: Union[str, None] = "f5c3d9e4b604"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

INDEX = "ix_audit_events_business_line"


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("business_line", sa.String(16), nullable=True, comment="业务线"))
    op.execute(
        """
        UPDATE audit_events
        SET business_line = split_part(module_code, '.', 1)
        WHERE business_line IS NULL AND split_part(module_code, '.', 1) IN ('policy', 'customer', 'tender')
        """
    )
    op.execute(
        """
        UPDATE audit_events
        SET business_line = changes->>'category'
        WHERE business_line IS NULL AND split_part(module_code, '.', 1) = 'ai'
          AND changes->>'category' IN ('policy', 'customer', 'tender')
        """
    )
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX}")
        op.execute(f"CREATE INDEX CONCURRENTLY {INDEX} ON audit_events (business_line)")
        op.execute(f"COMMENT ON INDEX {INDEX} IS '按类型筛选'")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX}")
    op.drop_column("audit_events", "business_line")
