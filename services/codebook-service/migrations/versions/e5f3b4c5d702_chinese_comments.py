"""add chinese table and column comments

Revision ID: e5f3b4c5d702
Revises: d4e2a3b4c601
Create Date: 2026-09-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e5f3b4c5d702"
down_revision: Union[str, None] = "d4e2a3b4c601"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


# 冻结此修订当时的表/列。历史迁移不能导入运行时模型：模型以后新增的列在这一步还不存在，
# 空库从头迁移会报 column does not exist（2026-09-24 加 codebook_outbox.lease_until 时踩到）。
COMMENTS = {'codebook_area_codes': {'comment': '省市区编码表',
                         'columns': {'id': '主键',
                                     'prov_id': '省份编码',
                                     'prov_name': '省份名称',
                                     'city_id': '城市编码',
                                     'city_name': '城市名称',
                                     'county_id': '区县编码',
                                     'county_name': '区县名称',
                                     'alias_prov_name': '省份别名',
                                     'alias_city_name': '城市别名',
                                     'alias_county_name': '区县别名',
                                     'city_name_short': '城市简称',
                                     'county_name_short': '区县简称',
                                     'version': '版本号',
                                     'created_at': '入库时间',
                                     'created_by_id': '入库人ID',
                                     'created_by_name': '入库人',
                                     'updated_at': '更新时间',
                                     'updated_by_id': '更新人ID',
                                     'updated_by_name': '操作人'}},
 'codebook_outbox': {'comment': '码表服务出站事件',
                     'columns': {'event_id': '事件ID',
                                 'event_type': '事件类型',
                                 'schema_version': '事件结构版本',
                                 'payload': '事件内容',
                                 'status': '投递状态',
                                 'attempts': '重试次数',
                                 'next_retry_at': '下次重试时间',
                                 'created_at': '创建时间',
                                 'error_message': '失败原因'}},
 'codebook_policy_types': {'comment': '政策类型码表',
                           'columns': {'id': '主键',
                                       'seq_no': '序号',
                                       'type_name': '政策类型',
                                       'definition': '定义',
                                       'version': '版本号',
                                       'created_at': '入库时间',
                                       'created_by_id': '入库人ID',
                                       'created_by_name': '入库人',
                                       'updated_at': '更新时间',
                                       'updated_by_id': '更新人ID',
                                       'updated_by_name': '操作人'}},
 'codebook_scenarios': {'comment': '行业场景码表',
                        'columns': {'id': '主键',
                                    'content_hash': '内容哈希',
                                    'industry_scenario_code': '行业场景编码',
                                    'industry_code': '行业编码',
                                    'industry_l1': '项目一级行业',
                                    'industry_l2': '项目二级行业',
                                    'industry_l3': '项目三级行业',
                                    'scenario_tag': '场景标签',
                                    'scenario_level': '场景level',
                                    'scenario_type': '场景类型',
                                    'desc_90': '场景描述(90字)',
                                    'desc_130': '场景描述(130字)',
                                    'desc_pest': '场景描述(PEST总结)',
                                    'scenario_source': '场景来源',
                                    'scenario_hierarchy': '场景层级',
                                    'scenario_code': '场景编码',
                                    'scenario_l1_name': '项目一级场景名称',
                                    'scenario_l1_desc': '项目一级场景描述',
                                    'scenario_l2_name': '项目二级场景名称',
                                    'scenario_l2_desc': '项目二级场景描述',
                                    'scenario_l3_name': '项目三级场景名称',
                                    'scenario_l3_desc': '项目三级场景描述',
                                    'customer_group_name': '客群名称',
                                    'customer_group_industry': '客群行业',
                                    'org_keywords': '机构及企业名称包含关键词',
                                    'scope_keywords': '经营范围包含',
                                    'customer_level': '客户等级',
                                    'customer_category': '客户类别',
                                    'product_l1_name': '项目一级产品名称',
                                    'product_l2_name': '项目二级产品名称',
                                    'branch_count': '下属分支机构数',
                                    'product_l1_sort': '一级产品排序（正序）',
                                    'product_l2_sort': '二级产品排序（正序）',
                                    'version': '版本号',
                                    'created_at': '入库时间',
                                    'created_by_id': '入库人ID',
                                    'created_by_name': '入库人',
                                    'updated_at': '更新时间',
                                    'updated_by_id': '更新人ID',
                                    'updated_by_name': '操作人'}}}


def _literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def _apply(clear: bool = False) -> None:
    for table, spec in COMMENTS.items():
        table_comment = None if clear else spec["comment"]
        op.execute(sa.text(f"COMMENT ON TABLE {table} IS {_literal(table_comment)}"))
        for column, column_comment in spec["columns"].items():
            comment = None if clear else column_comment
            op.execute(sa.text(f"COMMENT ON COLUMN {table}.{column} IS {_literal(comment)}"))


def upgrade() -> None:
    _apply()


def downgrade() -> None:
    _apply(clear=True)
