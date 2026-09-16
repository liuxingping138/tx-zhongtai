"""p2 iam public tables

Revision ID: b2a91c04e110
Revises: d1d3e76de821
Create Date: 2026-09-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b2a91c04e110"
down_revision: Union[str, None] = "d1d3e76de821"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "iam_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username", name="uq_iam_users_username"),
    )
    op.create_table(
        "iam_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_iam_roles_code"),
    )
    op.create_table(
        "iam_user_roles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("iam_users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("iam_roles.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "role_id", name="uq_iam_user_roles_user_role"),
    )
    op.create_table(
        "iam_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("iam_resources.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("service_code", sa.String(64), nullable=False),
        sa.Column("node_type", sa.String(16), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("code", name="uq_iam_resources_code"),
    )
    op.create_table(
        "iam_resource_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("iam_resources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action_code", sa.String(64), nullable=False),
        sa.Column("required_level", sa.String(8), nullable=False),
        sa.UniqueConstraint("resource_id", "action_code", name="uq_iam_resource_actions_resource_action"),
    )
    op.create_table(
        "iam_role_grants",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("iam_roles.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("iam_resources.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("level", sa.String(8), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("role_id", "resource_id", name="uq_iam_role_grants_role_resource"),
    )
    op.create_table(
        "iam_menu_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("iam_menu_items.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("route_name", sa.String(128), nullable=True),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("iam_resources.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("icon", sa.String(64), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "iam_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("iam_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_iam_sessions_user_id", "iam_sessions", ["user_id"])
    op.create_index("ix_iam_sessions_family_id", "iam_sessions", ["family_id"])
    op.create_index("ix_iam_sessions_expires_at", "iam_sessions", ["expires_at"])
    op.create_table(
        "iam_refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("iam_sessions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_iam_refresh_tokens_token_hash"),
    )
    op.create_index("ix_iam_refresh_tokens_session_id", "iam_refresh_tokens", ["session_id"])
    op.create_table(
        "iam_outbox",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_iam_outbox_status", "iam_outbox", ["status"])
    op.create_index("ix_iam_outbox_next_retry_at", "iam_outbox", ["next_retry_at"])


def downgrade() -> None:
    op.drop_table("iam_outbox")
    op.drop_table("iam_refresh_tokens")
    op.drop_table("iam_sessions")
    op.drop_table("iam_menu_items")
    op.drop_table("iam_role_grants")
    op.drop_table("iam_resource_actions")
    op.drop_table("iam_user_roles")
    op.drop_table("iam_resources")
    op.drop_table("iam_roles")
    op.drop_table("iam_users")
