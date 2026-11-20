"""上下文缓存：模型配缓存单价，任务、费用流水、试发用量记命中缓存的 token

命中缓存的输入按缓存价算钱。已有的三个方舟接入点按 2026-11 方舟控制台补上缓存价，已经填过的不覆盖；
没配缓存价的模型按输入价算，和原来一样。

Revision ID: d6f9b2c31616
Revises: c5e8a1b21515
Create Date: 2026-11-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d6f9b2c31616"
down_revision: Union[str, None] = "c5e8a1b21515"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

# 冻结在迁移里，不 import 运行时代码。接入点 → (缓存价, 高峰缓存价)，元/千token。
_CACHE_PRICES: dict[str, tuple[str, str | None]] = {
    "ep-20260915173105-gv9tb": ("0.0001", None),  # DeepSeek-V4-Flash 正式版
    "ep-20261021162727-fcx55": ("0.000016", "0.000032"),  # DeepSeek-V4.1-Flash 经济版，工作日高峰翻倍
    "ep-20260915170840-m8pwt": ("0.0003", None),  # DeepSeek-V4-Pro 正式版
}
_TOKEN_TABLES = (("ai_batch_runs", sa.BigInteger()), ("ai_run_costs", sa.BigInteger()), ("ai_call_usages", sa.Integer()))


def upgrade() -> None:
    op.add_column(
        "ai_models", sa.Column("cache_price", sa.Numeric(12, 6), nullable=True, comment="缓存输入单价（元/千token）")
    )
    op.add_column(
        "ai_models",
        sa.Column("peak_cache_price", sa.Numeric(12, 6), nullable=True, comment="高峰缓存单价（元/千token）"),
    )
    for table, kind in _TOKEN_TABLES:
        op.add_column(table, sa.Column("cached_tokens", kind, nullable=False, server_default="0", comment="缓存命中token"))
    update = sa.text(
        "UPDATE ai_models SET cache_price = CAST(:cache AS NUMERIC(12, 6)),"
        " peak_cache_price = CAST(:peak AS NUMERIC(12, 6))"
        " WHERE endpoint = :endpoint AND cache_price IS NULL AND peak_cache_price IS NULL"
    )
    for endpoint, (cache, peak) in _CACHE_PRICES.items():
        op.execute(update.bindparams(endpoint=endpoint, cache=cache, peak=peak))


def downgrade() -> None:
    for table, _ in reversed(_TOKEN_TABLES):
        op.drop_column(table, "cached_tokens")
    op.drop_column("ai_models", "peak_cache_price")
    op.drop_column("ai_models", "cache_price")
