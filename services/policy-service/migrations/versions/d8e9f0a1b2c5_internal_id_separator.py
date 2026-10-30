"""信源内部唯一 id 的四个字段之间加分隔符，按新算法重算已有的 id

原来是 md5(网站名称 + 省份 + 地市 + 标签) 直接拼接，("ab","c") 和 ("a","bc") 算出同一个 id，两个不同的信源会被当成重复。
现在字段之间夹一个单元分隔符 U+001F（app/policy/application/region.make_internal_id）。PostgreSQL 的 md5(text) 对 UTF-8 字节求摘要，
和 Python 的结果一致，所以在库里一条 UPDATE 重算。新算法区分得更细：原来不重复的，重算后也不会重复，唯一约束不会撞。
内部唯一 id 只用来查重，导入时都按字段现算，导出的旧值不会再被读回来。

Revision ID: d8e9f0a1b2c5
Revises: c7d8e9f0a1b4
Create Date: 2026-10-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "d8e9f0a1b2c5"
down_revision: Union[str, None] = "c7d8e9f0a1b4"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE policy_sources SET internal_id = "
        "md5(site_name || chr(31) || province_name || chr(31) || city_name || chr(31) || tag)"
    )


def downgrade() -> None:
    # 回到直接拼接：期间新建了只靠分隔符才区分得开的信源时会撞唯一约束，那种情况要先处理掉重复的再回退。
    op.execute("UPDATE policy_sources SET internal_id = md5(site_name || province_name || city_name || tag)")
