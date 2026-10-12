"""爬虫监测资源编码去掉 v2：原地改编码，角色授权跟着资源 ID 走，不用重新分配

菜单 ID 由菜单编码算出，这里删掉旧编码那一行，清单同步时按新编码建回来。

Revision ID: a3d6f9b1c720
Revises: e6a3c8d51f22
Create Date: 2026-10-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "a3d6f9b1c720"
down_revision: Union[str, None] = "e6a3c8d51f22"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

OLD_CODE = "policy.crawler_monitoring_v2"
NEW_CODE = "policy.crawler_monitoring"
# uuid5(seed._NS, "menu:<菜单编码>")
OLD_MENU_ID = "ec40114e-a5c4-5e3b-8411-3d9e952b39ae"
NEW_MENU_ID = "67574ecf-6244-591e-a847-fc3d8493f269"


def _drop_resource(code: str) -> None:
    ids = f"(SELECT id FROM iam_resources WHERE code = '{code}')"
    op.execute(f"DELETE FROM iam_menu_items WHERE resource_id IN {ids}")
    op.execute(f"DELETE FROM iam_role_grants WHERE resource_id IN {ids}")
    op.execute(f"DELETE FROM iam_resource_actions WHERE resource_id IN {ids}")
    op.execute(f"DELETE FROM iam_resources WHERE code = '{code}'")


def upgrade() -> None:
    # 新编码以前是已下线的旧版爬虫监测，清单同步通常已删掉；万一残留先清掉，否则改名撞唯一约束。
    if op.get_bind().exec_driver_sql(f"SELECT 1 FROM iam_resources WHERE code = '{OLD_CODE}'").first():
        _drop_resource(NEW_CODE)
    op.execute(f"DELETE FROM iam_menu_items WHERE id = '{OLD_MENU_ID}'")
    op.execute(f"UPDATE iam_resources SET code = '{NEW_CODE}' WHERE code = '{OLD_CODE}'")


def downgrade() -> None:
    op.execute(f"DELETE FROM iam_menu_items WHERE id = '{NEW_MENU_ID}'")
    op.execute(f"UPDATE iam_resources SET code = '{OLD_CODE}' WHERE code = '{NEW_CODE}'")
