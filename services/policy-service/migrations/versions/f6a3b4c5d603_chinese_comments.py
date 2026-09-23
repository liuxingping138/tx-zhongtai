"""add chinese table and column comments

Revision ID: f6a3b4c5d603
Revises: e5f2a3b4c502
Create Date: 2026-09-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f6a3b4c5d603"
down_revision: Union[str, None] = "e5f2a3b4c502"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


# 冻结此修订当时的表/列，历史迁移不能导入未来的运行时模型。
COMMENTS = {'policy_base_tags': {'comment': '政策基础标签表',
                      'columns': {'id': '主键',
                                  'content_hash': '内容哈希',
                                  'policy_name': '政策名称',
                                  'issuing_dept': '出台部门',
                                  'issuer_industry': '发文机构行业',
                                  'policy_level': '政策层级',
                                  'province_code': '省份编码',
                                  'province_name': '省份名称',
                                  'city_code': '地市编码',
                                  'city_name': '地市名称',
                                  'issued_at': '当前政策出台时间',
                                  'policy_types': '政策类型',
                                  'source_url': '原始网站链接',
                                  'is_penetrate': '是否穿透',
                                  'penetrate_words': '穿透词',
                                  'penetrate_score': '穿透词评分',
                                  'need_interpret': '是否解读',
                                  'remark': '备注',
                                  'version': '版本号',
                                  'created_at': '入库时间',
                                  'created_by_id': '入库人ID',
                                  'created_by_name': '入库人',
                                  'updated_at': '更新时间',
                                  'updated_by_id': '更新人ID',
                                  'updated_by_name': '操作人'}},
 'policy_interpretations': {'comment': '政策解读列表',
                            'columns': {'id': '主键',
                                        'record_id': '自增或雪花算法',
                                        'tenant_id': '租户ID',
                                        'policy_uid': '政策唯一标识',
                                        'policy_title': '政策原文名称',
                                        'industry_scenario_code': '行业场景编码',
                                        'industry_code': '行业编码',
                                        'industry_l1': '一级行业',
                                        'industry_l2': '二级行业',
                                        'industry_l3': '三级行业',
                                        'scenario_code': '场景编码',
                                        'scenario_l1_name': '一级场景名称',
                                        'scenario_l2_name': '二级场景名称',
                                        'scenario_l3_name': '三级场景名称',
                                        'target_customers': '目标客户当前政策影响客户群',
                                        'relation_key': '关联主键',
                                        'opportunity_type': '机会类型',
                                        'policy_summary': '政策要文',
                                        'has_subsidy': '有无政府补贴',
                                        'subsidy_content': '补贴内容',
                                        'market_opportunity': '政策市场机会',
                                        'info_level': '信息化等级',
                                        'is_new_scenario': '是否新增场景',
                                        'new_scenario_level': '新增场景级别',
                                        'version': '版本号',
                                        'created_at': '入库时间',
                                        'created_by_id': '入库人ID',
                                        'created_by_name': '入库人',
                                        'updated_at': '更新时间',
                                        'updated_by_id': '更新人ID',
                                        'updated_by_name': '操作人'}},
 'policy_outbox': {'comment': '政策服务出站事件',
                   'columns': {'event_id': '事件ID',
                               'event_type': '事件类型',
                               'schema_version': '事件结构版本',
                               'payload': '事件内容',
                               'status': '投递状态',
                               'attempts': '重试次数',
                               'next_retry_at': '下次重试时间',
                               'created_at': '创建时间',
                               'error_message': '失败原因'}},
 'policy_sources': {'comment': '信源管理',
                    'columns': {'id': '主键',
                                'internal_id': '内部唯一id',
                                'site_code': '网站编码',
                                'province_name': '省份',
                                'province_code': '省份编码',
                                'city_name': '地市',
                                'city_code': '地市编码',
                                'district_name': '区县',
                                'district_code': '区县编码',
                                'site_name': '网站名称',
                                'crawl_priority': '网站梳理和抓取的优先级',
                                'url': '链接',
                                'tag': '标签',
                                'data_type': '数据类型',
                                'department': '所属部门',
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
        for column, value in spec["columns"].items():
            comment = None if clear else value
            op.execute(sa.text(f"COMMENT ON COLUMN {table}.{column} IS {_literal(comment)}"))


def upgrade() -> None:
    _apply()


def downgrade() -> None:
    _apply(clear=True)
