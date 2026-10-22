"""已爬但没填上线时间的信源，上线时间统一记为 2026-10-22（「改成已爬自动记上线时间」功能上线当天）

Revision ID: d5e6f7a8b823
Revises: c4d5e6f7a722
Create Date: 2026-10-22
"""

from alembic import op

revision = "d5e6f7a8b823"
down_revision = "c4d5e6f7a722"
branch_labels = None
depends_on = None

BACKFILL_DATE = "2026-10-22"


def upgrade():
    # 用户确认：历史上线时间无从考证，统一填功能上线当天，之后新上线的按改状态当天自动记。
    op.execute(
        "UPDATE policy_sources SET online_date = '" + BACKFILL_DATE + "' "
        "WHERE crawler_status = '已爬' AND online_date = ''"
    )


def downgrade():
    # 只能按日期回退：当天手动或自动记的上线时间也会一并清掉。
    op.execute("UPDATE policy_sources SET online_date = '' WHERE online_date = '" + BACKFILL_DATE + "'")
