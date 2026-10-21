"""大模型配置改成存库，在「模型配置」页维护；写入原先写在代码里的模型

价格按 2026-10-21 方舟控制台：Flash、Pro 默认低优档 + 思考强度 low，V4.1-Flash 经济版不支持低优、按高峰/空闲分时计价。

Revision ID: d4f7b0c50404
Revises: c3e6a9b40303
Create Date: 2026-10-21
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4f7b0c50404"
down_revision: Union[str, None] = "c3e6a9b40303"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

_FLASH = "ep-20260915173105-gv9tb"
_ARK = {"provider": "ark", "thinking": "enabled", "reasoning_effort": "low", "search_price": Decimal(0)}
_FLASH_PRICES = {
    "service_tier": "flex",
    "input_price": Decimal("0.003"),
    "output_price": Decimal("0.009"),
    "flex_input_price": Decimal("0.0015"),
    "flex_output_price": Decimal("0.0045"),
    "rate_limit": "常规：500 RPM、1000000 TPM；低优：200000 TPM",
}
_BAIDU = {
    "provider": "baidu",
    "web_search": False,
    "thinking": "switch",
    "reasoning_effort": "",
    "service_tier": "",
    "input_price": Decimal("0.001"),
    "output_price": Decimal("0.005"),
    "search_price": Decimal(0),
}
# 冻结在迁移里，不 import 运行时代码：以后模型或字段变了，这一步从空库迁移仍然成立。
SEED: list[dict[str, Any]] = [
    {
        **_ARK,
        **_FLASH_PRICES,
        "id": "deepseek-v4-flash",
        "name": "字节-DeepSeek-V4-Flash（联网）",
        "endpoint": _FLASH,
        "web_search": True,
        "search_price": Decimal("0.004"),
    },
    {
        **_ARK,
        **_FLASH_PRICES,
        "id": "deepseek-v4-flash-nw",
        "name": "字节-DeepSeek-V4-Flash（不联网）",
        "endpoint": _FLASH,
        "web_search": False,
    },
    {
        **_ARK,
        "id": "deepseek-v41-flash",
        "name": "字节-DeepSeek-V4.1-Flash经济版（不联网）",
        "endpoint": "ep-20261021162727-fcx55",
        "web_search": False,
        "service_tier": "",
        "input_price": Decimal("0.0008"),
        "output_price": Decimal("0.0032"),
        "peak_input_price": Decimal("0.0016"),
        "peak_output_price": Decimal("0.0064"),
        "peak_hours": "09:00-12:00,14:00-18:00",
        "rate_limit": "3000 RPM、5000000 TPM",
    },
    {
        **_ARK,
        "id": "deepseek-v4-pro正式版",
        "name": "字节-DeepSeek-V4-Pro（不联网）",
        "endpoint": "ep-20260915170840-m8pwt",
        "web_search": False,
        "service_tier": "flex",
        "input_price": Decimal("0.0135"),
        "output_price": Decimal("0.027"),
        "flex_input_price": Decimal("0.0045"),
        "flex_output_price": Decimal("0.009"),
        "rate_limit": "常规：500 RPM、1000000 TPM；低优：200000 TPM",
    },
    {**_BAIDU, "id": "baidu-deepseek-v3.2", "name": "百度-DeepSeek-V3.2", "endpoint": "deepseek-v3.2"},
    {**_BAIDU, "id": "baidu-deepseek-v4-flash", "name": "百度-DeepSeek-V4-Flash", "endpoint": "deepseek-v4-flash"},
]


def _price(name: str, comment: str, *, nullable: bool = False) -> sa.Column[Any]:
    return sa.Column(name, sa.Numeric(12, 6), nullable=nullable, comment=comment)


def upgrade() -> None:
    table = op.create_table(
        "ai_models",
        sa.Column("id", sa.String(64), primary_key=True, comment="模型ID"),
        sa.Column("name", sa.String(100), nullable=False, comment="显示名称"),
        sa.Column("provider", sa.String(16), nullable=False, comment="厂商"),
        sa.Column("endpoint", sa.String(128), nullable=False, comment="接入点"),
        sa.Column("web_search", sa.Boolean(), nullable=False, server_default=sa.false(), comment="联网搜索"),
        sa.Column("thinking", sa.String(16), nullable=False, server_default="", comment="深度思考"),
        sa.Column("reasoning_effort", sa.String(16), nullable=False, server_default="", comment="思考强度"),
        sa.Column("service_tier", sa.String(16), nullable=False, server_default="", comment="服务档位"),
        _price("input_price", "常规输入单价(元/千token)"),
        _price("output_price", "常规输出单价(元/千token)"),
        _price("flex_input_price", "低优输入单价(元/千token)", nullable=True),
        _price("flex_output_price", "低优输出单价(元/千token)", nullable=True),
        _price("peak_input_price", "高峰输入单价(元/千token)", nullable=True),
        _price("peak_output_price", "高峰输出单价(元/千token)", nullable=True),
        sa.Column("peak_hours", sa.String(100), nullable=False, server_default="", comment="高峰时段"),
        _price("search_price", "联网单价(元/次)"),
        sa.Column("rate_limit", sa.Text(), nullable=False, server_default="", comment="限流说明"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true(), comment="是否启用"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0", comment="排序"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1", comment="版本号"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="创建时间"),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default="", comment="创建人"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="更新时间"),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default="", comment="更新人"),
        comment="大模型配置",
    )
    now = datetime.now(UTC)
    defaults = {
        "flex_input_price": None,
        "flex_output_price": None,
        "peak_input_price": None,
        "peak_output_price": None,
        "peak_hours": "",
        "rate_limit": "",
    }
    op.bulk_insert(
        table,
        [
            {**defaults, **row, "enabled": True, "sort_order": (index + 1) * 10, "version": 1,
             "created_at": now, "created_by_name": "系统", "updated_at": now, "updated_by_name": "系统"}
            for index, row in enumerate(SEED)
        ],
    )


def downgrade() -> None:
    op.drop_table("ai_models")
