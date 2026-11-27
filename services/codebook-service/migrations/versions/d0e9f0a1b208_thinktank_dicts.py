"""新增智库专属 6 张码表（统一归一化表 codebook_thinktank_dicts）并幂等灌入初始种子。

Revision ID: d0e9f0a1b208
Revises: c9d8e9f0a107
Create Date: 2026-11-27
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d0e9f0a1b208"
down_revision: Union[str, None] = "c9d8e9f0a107"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

_SEED_NAMESPACE = uuid.UUID("7a4e2c91-5d3b-4f80-8e12-9b6a1c3d5e77")

_INITIAL_SEEDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "file_types",
        (
            "经分",
            "通报",
            "工作会",
            "行业营销指引",
            "工作部署&专项行动",
            "网络规划",
            "考核",
            "产品",
            "政企改革&数字化",
            "客户视图",
            "通知",
            "渠道&生态",
            "国际业务",
            "其他",
        ),
    ),
    (
        "departments",
        (
            "政企部",
            "市场部",
            "工业行业事业部",
            "公众客户销售中心",
            "国际部",
            "集团商业客户拓展部",
            "集团政企应急行业事业部",
            "交通物流行业事业部",
            "柯瑞文董事长",
        ),
    ),
    (
        "industries",
        (
            "党政",
            "工业能源",
            "教育",
            "医卫",
            "交通物流",
            "IT互联网",
            "金融",
            "农业",
            "住建",
            "文旅",
            "中小",
            "无",
        ),
    ),
    (
        "product_types",
        (
            "云",
            "网",
            "数",
            "智",
            "安",
            "语音",
            "消息",
            "数字平台",
            "量子",
            "解决方案",
            "服务",
            "无",
        ),
    ),
    (
        "provinces",
        (
            "集团",
            "北京市",
            "天津市",
            "河北省",
            "山西省",
            "内蒙古自治区",
            "辽宁省",
            "吉林省",
            "黑龙江省",
            "上海市",
            "江苏省",
            "浙江省",
            "安徽省",
            "福建省",
            "江西省",
            "山东省",
            "河南省",
            "湖北省",
            "湖南省",
            "广东省",
            "广西壮族自治区",
            "海南省",
            "重庆市",
            "四川省",
            "贵州省",
            "云南省",
            "西藏自治区",
            "陕西省",
            "甘肃省",
            "青海省",
            "宁夏回族自治区",
            "新疆维吾尔自治区",
        ),
    ),
    (
        "market_categories",
        (
            "行客",
            "商客",
            "综合",
            "无",
        ),
    ),
)


def upgrade() -> None:
    op.create_table(
        "codebook_thinktank_dicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, comment="主键"),
        sa.Column("dict_type", sa.String(32), nullable=False, comment="码表类型"),
        sa.Column("name", sa.String(128), nullable=False, comment="名称"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0", comment="排序"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1", comment="版本号"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="入库时间"),
        sa.Column("created_by_id", sa.String(64), nullable=False, comment="入库人ID"),
        sa.Column("created_by_name", sa.String(128), nullable=False, comment="入库人"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="更新时间"),
        sa.Column("updated_by_id", sa.String(64), nullable=False, comment="更新人ID"),
        sa.Column("updated_by_name", sa.String(128), nullable=False, comment="操作人"),
        sa.UniqueConstraint("dict_type", "name", name="uq_codebook_thinktank_dicts_type_name"),
        comment="智库专属码表",
    )
    op.create_index("ix_codebook_thinktank_dicts_dict_type", "codebook_thinktank_dicts", ["dict_type"])

    table = sa.table(
        "codebook_thinktank_dicts",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("dict_type", sa.String(32)),
        sa.column("name", sa.String(128)),
        sa.column("sort_order", sa.Integer()),
        sa.column("version", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("created_by_id", sa.String(64)),
        sa.column("created_by_name", sa.String(128)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("updated_by_id", sa.String(64)),
        sa.column("updated_by_name", sa.String(128)),
    )
    now = datetime.now(UTC)
    rows = [
        {
            "id": uuid.uuid5(_SEED_NAMESPACE, f"{dict_type}:{name}"),
            "dict_type": dict_type,
            "name": name,
            "sort_order": idx,
            "version": 1,
            "created_at": now,
            "created_by_id": "system",
            "created_by_name": "系统初始化",
            "updated_at": now,
            "updated_by_id": "system",
            "updated_by_name": "系统初始化",
        }
        for dict_type, values in _INITIAL_SEEDS
        for idx, name in enumerate(values, start=1)
    ]
    stmt = (
        postgresql.insert(table)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_codebook_thinktank_dicts_type_name")
    )
    op.execute(stmt)


def downgrade() -> None:
    op.drop_index("ix_codebook_thinktank_dicts_dict_type", table_name="codebook_thinktank_dicts")
    op.drop_table("codebook_thinktank_dicts")
