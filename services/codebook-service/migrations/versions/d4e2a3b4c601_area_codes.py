"""add codebook area codes

Revision ID: d4e2a3b4c601
Revises: c3d0e1f2a301
Create Date: 2026-09-18

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e2a3b4c601"
down_revision: Union[str, None] = "c3d0e1f2a301"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "codebook_area_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("prov_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("prov_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("city_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("city_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("county_id", sa.String(64), nullable=False),
        sa.Column("county_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("alias_prov_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("alias_city_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("alias_county_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("city_name_short", sa.String(200), nullable=False, server_default=""),
        sa.Column("county_name_short", sa.String(200), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_id", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False),
        sa.UniqueConstraint("county_id", name="uq_codebook_area_codes_county_id"),
    )
    op.create_index("ix_codebook_area_codes_prov_name", "codebook_area_codes", ["prov_name"])
    op.create_index("ix_codebook_area_codes_city_name", "codebook_area_codes", ["city_name"])
    op.create_index("ix_codebook_area_codes_county_name", "codebook_area_codes", ["county_name"])


def downgrade() -> None:
    op.drop_index("ix_codebook_area_codes_county_name", table_name="codebook_area_codes")
    op.drop_index("ix_codebook_area_codes_city_name", table_name="codebook_area_codes")
    op.drop_index("ix_codebook_area_codes_prov_name", table_name="codebook_area_codes")
    op.drop_table("codebook_area_codes")
