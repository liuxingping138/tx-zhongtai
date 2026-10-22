"""政策 AI 打标的正文默认全文照传（正文截取字数 0 表示不截断），已有设置一并改成全文

Revision ID: c4d5e6f7a722
Revises: b3c4d5e6f621
Create Date: 2026-10-22
"""

from alembic import op

revision = "c4d5e6f7a722"
down_revision = "b3c4d5e6f621"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("policy_ai_config", "content_max_chars", server_default="0", comment="正文截取字数（0 为全文）")
    # 用户确认正文要全部传：原来的默认 15000 字截断改成全文。
    op.execute("UPDATE policy_ai_config SET content_max_chars = 0 WHERE content_max_chars = 15000")


def downgrade():
    op.alter_column("policy_ai_config", "content_max_chars", server_default="15000", comment="正文截取字数")
