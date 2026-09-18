"""init policy tables

Revision ID: d4e1f2a3b401
Revises:
Create Date: 2026-09-18

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e1f2a3b401"
down_revision: Union[str, None] = None
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policy_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("internal_id", sa.String(32), nullable=False),
        sa.Column("site_code", sa.String(16), nullable=False),
        sa.Column("province_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("province_code", sa.String(8), nullable=False, server_default=""),
        sa.Column("city_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("city_code", sa.String(8), nullable=False, server_default=""),
        sa.Column("district_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("district_code", sa.String(8), nullable=False, server_default=""),
        sa.Column("site_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("crawl_priority", sa.String(255), nullable=False, server_default=""),
        sa.Column("url", sa.Text(), nullable=False, server_default=""),
        sa.Column("tag", sa.Text(), nullable=False, server_default=""),
        sa.Column("data_type", sa.Text(), nullable=False, server_default=""),
        sa.Column("department", sa.String(255), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_id", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False),
        sa.UniqueConstraint("internal_id", name="uq_policy_sources_internal_id"),
        sa.UniqueConstraint("site_code", name="uq_policy_sources_site_code"),
    )
    op.create_index("ix_policy_sources_province_code", "policy_sources", ["province_code"])
    op.create_index("ix_policy_sources_city_code", "policy_sources", ["city_code"])
    op.create_index("ix_policy_sources_district_code", "policy_sources", ["district_code"])
    op.create_index("ix_policy_sources_site_name", "policy_sources", ["site_name"])

    op.create_table(
        "policy_base_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("policy_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("issuing_dept", sa.String(255), nullable=False, server_default=""),
        sa.Column("issuer_industry", sa.String(255), nullable=False, server_default=""),
        sa.Column("policy_level", sa.String(64), nullable=False, server_default=""),
        sa.Column("province_code", sa.String(16), nullable=False, server_default=""),
        sa.Column("province_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("city_code", sa.String(16), nullable=False, server_default=""),
        sa.Column("city_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("issued_at", sa.String(64), nullable=False, server_default=""),
        sa.Column("policy_types", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_penetrate", sa.String(32), nullable=False, server_default=""),
        sa.Column("penetrate_words", sa.Text(), nullable=False, server_default=""),
        sa.Column("penetrate_score", sa.String(64), nullable=False, server_default=""),
        sa.Column("need_interpret", sa.String(64), nullable=False, server_default=""),
        sa.Column("remark", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_id", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False),
        sa.UniqueConstraint("content_hash", name="uq_policy_base_tags_hash"),
    )
    op.create_index("ix_policy_base_tags_province_name", "policy_base_tags", ["province_name"])

    op.create_table(
        "policy_interpretations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("record_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("policy_uid", sa.String(64), nullable=False, server_default=""),
        sa.Column("policy_title", sa.Text(), nullable=False, server_default=""),
        sa.Column("industry_scenario_code", sa.String(128), nullable=False, server_default=""),
        sa.Column("industry_code", sa.String(32), nullable=False, server_default=""),
        sa.Column("industry_l1", sa.String(128), nullable=False, server_default=""),
        sa.Column("industry_l2", sa.String(128), nullable=False, server_default=""),
        sa.Column("industry_l3", sa.String(128), nullable=False, server_default=""),
        sa.Column("scenario_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("scenario_l1_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("scenario_l2_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("scenario_l3_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("target_customers", sa.Text(), nullable=False, server_default=""),
        sa.Column("relation_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("opportunity_type", sa.String(64), nullable=False, server_default=""),
        sa.Column("policy_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("has_subsidy", sa.String(32), nullable=False, server_default=""),
        sa.Column("subsidy_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("market_opportunity", sa.Text(), nullable=False, server_default=""),
        sa.Column("info_level", sa.String(32), nullable=False, server_default=""),
        sa.Column("is_new_scenario", sa.String(32), nullable=False, server_default=""),
        sa.Column("new_scenario_level", sa.String(64), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_id", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False),
        sa.UniqueConstraint("relation_key", name="uq_policy_interpretations_relation_key"),
    )
    op.create_index("ix_policy_interpretations_policy_uid", "policy_interpretations", ["policy_uid"])
    op.create_index(
        "ix_policy_interpretations_industry_scenario_code", "policy_interpretations", ["industry_scenario_code"]
    )
    op.create_index("ix_policy_interpretations_industry_l1", "policy_interpretations", ["industry_l1"])

    op.create_table(
        "policy_outbox",
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
    op.create_index("ix_policy_outbox_status", "policy_outbox", ["status"])
    op.create_index("ix_policy_outbox_next_retry_at", "policy_outbox", ["next_retry_at"])


def downgrade() -> None:
    op.drop_table("policy_outbox")
    op.drop_table("policy_interpretations")
    op.drop_table("policy_base_tags")
    op.drop_table("policy_sources")
