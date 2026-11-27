"""智库访问 IP 白名单

Revision ID: c3d4e5f6a703
Revises: b2c3d4e5f602
Create Date: 2026-11-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a703"
down_revision: Union[str, None] = "b2c3d4e5f602"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "thinktank_ip_whitelist",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, comment="主键"),
        sa.Column("ip_range", sa.String(64), nullable=False, comment="IP或网段"),
        sa.Column("holder", sa.String(64), nullable=False, comment="使用人"),
        sa.Column("reason", sa.String(500), nullable=False, server_default="", comment="开通原因"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, comment="到期时间"),
        sa.Column("created_by_id", sa.String(64), nullable=False, comment="开通人ID"),
        sa.Column("created_by_name", sa.String(128), nullable=False, comment="开通人"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="开通时间"),
        sa.Column("updated_by_id", sa.String(64), nullable=False, comment="最后修改人ID"),
        sa.Column("updated_by_name", sa.String(128), nullable=False, comment="最后修改人"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="最后修改时间"),
        comment="智库访问IP白名单",
    )
    op.create_index("ix_thinktank_ipw_expires_at", "thinktank_ip_whitelist", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_thinktank_ipw_expires_at", table_name="thinktank_ip_whitelist")
    op.drop_table("thinktank_ip_whitelist")
