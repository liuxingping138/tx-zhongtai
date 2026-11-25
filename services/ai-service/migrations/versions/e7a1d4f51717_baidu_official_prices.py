"""校准百度千帆 DeepSeek-V3.2 与 DeepSeek-V4-Flash 官方标准单价及缓存命中价

初始种子（d4f7b0c50404）把百度两条模型都填成了占位值 0.001 / 0.005 且未配缓存价。
按百度智能云千帆 ModelBuilder 官方按量后付费标准价（换算为元/千 token）校准仍处于初始占位状态的记录：
- 百度-DeepSeek-V3.2（0~32K）：输入 0.002（2 元/百万）、输出 0.003（3 元/百万）、缓存命中 0.0002（0.2 元/百万）
- 百度-DeepSeek-V4-Flash：输入 0.001（1 元/百万）、输出 0.002（2 元/百万）、缓存命中 0.00002（0.02 元/百万）
人工在页面上改过（cache_price 已非空或价格已变更）的记录不覆盖。

Revision ID: e7a1d4f51717
Revises: d6f9b2c31616
Create Date: 2026-11-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7a1d4f51717"
down_revision: Union[str, None] = "d6f9b2c31616"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

_BAIDU_OFFICIAL: tuple[tuple[str, str, str, str], ...] = (
    ("baidu-deepseek-v3.2", "0.002", "0.003", "0.0002"),
    ("baidu-deepseek-v4-flash", "0.001", "0.002", "0.00002"),
)


def upgrade() -> None:
    stmt = sa.text(
        "UPDATE ai_models"
        " SET input_price = CAST(:inp AS NUMERIC(12, 6)),"
        "     output_price = CAST(:outp AS NUMERIC(12, 6)),"
        "     cache_price = CAST(:cache AS NUMERIC(12, 6))"
        " WHERE id = :id"
        "   AND input_price = CAST('0.001' AS NUMERIC(12, 6))"
        "   AND output_price = CAST('0.005' AS NUMERIC(12, 6))"
        "   AND cache_price IS NULL"
    )
    for model_id, inp, outp, cache in _BAIDU_OFFICIAL:
        op.execute(stmt.bindparams(id=model_id, inp=inp, outp=outp, cache=cache))


def downgrade() -> None:
    stmt = sa.text(
        "UPDATE ai_models"
        " SET input_price = CAST('0.001' AS NUMERIC(12, 6)),"
        "     output_price = CAST('0.005' AS NUMERIC(12, 6)),"
        "     cache_price = NULL"
        " WHERE id = :id"
        "   AND input_price = CAST(:inp AS NUMERIC(12, 6))"
        "   AND output_price = CAST(:outp AS NUMERIC(12, 6))"
        "   AND cache_price = CAST(:cache AS NUMERIC(12, 6))"
    )
    for model_id, inp, outp, cache in _BAIDU_OFFICIAL:
        op.execute(stmt.bindparams(id=model_id, inp=inp, outp=outp, cache=cache))
