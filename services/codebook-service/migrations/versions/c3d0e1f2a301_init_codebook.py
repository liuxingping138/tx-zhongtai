"""init codebook tables

Revision ID: c3d0e1f2a301
Revises:
Create Date: 2026-09-18

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d0e1f2a301"
down_revision: Union[str, None] = None
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "codebook_policy_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("seq_no", sa.String(32), nullable=False, server_default=""),
        sa.Column("type_name", sa.String(64), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_id", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False),
        sa.UniqueConstraint("type_name", name="uq_codebook_policy_types_name"),
    )
    op.create_table(
        "codebook_scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("industry_scenario_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("industry_code", sa.String(32), nullable=False, server_default=""),
        sa.Column("industry_l1", sa.String(128), nullable=False, server_default=""),
        sa.Column("industry_l2", sa.String(128), nullable=False, server_default=""),
        sa.Column("industry_l3", sa.String(128), nullable=False, server_default=""),
        sa.Column("scenario_tag", sa.String(255), nullable=False, server_default=""),
        sa.Column("scenario_level", sa.String(16), nullable=False, server_default=""),
        sa.Column("scenario_type", sa.String(16), nullable=False, server_default=""),
        sa.Column("desc_90", sa.Text(), nullable=False, server_default=""),
        sa.Column("desc_130", sa.Text(), nullable=False, server_default=""),
        sa.Column("desc_pest", sa.Text(), nullable=False, server_default=""),
        sa.Column("scenario_source", sa.Text(), nullable=False, server_default=""),
        sa.Column("scenario_hierarchy", sa.String(64), nullable=False, server_default=""),
        sa.Column("scenario_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("scenario_l1_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("scenario_l1_desc", sa.Text(), nullable=False, server_default=""),
        sa.Column("scenario_l2_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("scenario_l2_desc", sa.Text(), nullable=False, server_default=""),
        sa.Column("scenario_l3_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("scenario_l3_desc", sa.Text(), nullable=False, server_default=""),
        sa.Column("customer_group_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("customer_group_industry", sa.String(255), nullable=False, server_default=""),
        sa.Column("org_keywords", sa.Text(), nullable=False, server_default=""),
        sa.Column("scope_keywords", sa.Text(), nullable=False, server_default=""),
        sa.Column("customer_level", sa.String(255), nullable=False, server_default=""),
        sa.Column("customer_category", sa.String(255), nullable=False, server_default=""),
        sa.Column("product_l1_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("product_l2_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("branch_count", sa.String(64), nullable=False, server_default=""),
        sa.Column("product_l1_sort", sa.String(32), nullable=False, server_default=""),
        sa.Column("product_l2_sort", sa.String(32), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_id", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False),
        sa.UniqueConstraint("content_hash", name="uq_codebook_scenarios_hash"),
    )
    op.create_index("ix_codebook_scenarios_industry_scenario_code", "codebook_scenarios", ["industry_scenario_code"])
    op.create_index("ix_codebook_scenarios_industry_l1", "codebook_scenarios", ["industry_l1"])
    op.create_index("ix_codebook_scenarios_scenario_tag", "codebook_scenarios", ["scenario_tag"])
    op.create_index("ix_codebook_scenarios_customer_group_name", "codebook_scenarios", ["customer_group_name"])
    op.create_table(
        "codebook_outbox",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_codebook_outbox_status", "codebook_outbox", ["status"])
    op.create_index("ix_codebook_outbox_next_retry_at", "codebook_outbox", ["next_retry_at"])


def downgrade() -> None:
    op.drop_table("codebook_outbox")
    op.drop_table("codebook_scenarios")
    op.drop_table("codebook_policy_types")
