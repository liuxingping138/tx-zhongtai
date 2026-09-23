"""add chinese table and column comments

Revision ID: e2c04f15a301
Revises: b2a91c04e110
Create Date: 2026-09-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e2c04f15a301"
down_revision: Union[str, None] = "b2a91c04e110"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


# 冻结此修订当时的表/列，历史迁移不能导入未来的运行时模型（否则新加列会让空库迁移失败）。
COMMENTS = {'iam_outbox': {'comment': '身份服务出站事件',
                'columns': {'event_id': '事件ID',
                            'event_type': '事件类型',
                            'schema_version': '事件结构版本',
                            'payload': '事件内容',
                            'status': '投递状态',
                            'attempts': '重试次数',
                            'next_retry_at': '下次重试时间',
                            'lease_until': '租约截止时间',
                            'created_at': '创建时间',
                            'error_message': '失败原因'}},
 'iam_resources': {'comment': '资源',
                   'columns': {'id': '主键',
                               'code': '资源编码',
                               'parent_id': '父资源ID',
                               'name': '资源名称',
                               'service_code': '所属服务',
                               'node_type': '节点类型',
                               'published': '是否发布',
                               'sort_order': '排序'}},
 'iam_roles': {'comment': '角色',
               'columns': {'id': '主键',
                           'code': '角色编码',
                           'name': '角色名称',
                           'status': '状态',
                           'is_builtin': '是否内置',
                           'version': '版本号',
                           'created_at': '创建时间',
                           'updated_at': '更新时间'}},
 'iam_users': {'comment': '用户',
               'columns': {'id': '主键',
                           'username': '用户名',
                           'display_name': '显示名',
                           'password_hash': '密码哈希',
                           'status': '状态',
                           'must_change_password': '必须改密',
                           'password_changed_at': '最近改密时间',
                           'version': '版本号',
                           'created_at': '创建时间',
                           'updated_at': '更新时间'}},
 'iam_menu_items': {'comment': '菜单项',
                    'columns': {'id': '主键',
                                'parent_id': '父菜单ID',
                                'title': '菜单标题',
                                'route_name': '路由名称',
                                'resource_id': '关联资源ID',
                                'icon': '图标',
                                'sort_order': '排序',
                                'enabled': '是否启用'}},
 'iam_resource_actions': {'comment': '资源动作',
                          'columns': {'id': '主键',
                                      'resource_id': '资源ID',
                                      'action_code': '动作编码',
                                      'required_level': '所需权限级别'}},
 'iam_role_grants': {'comment': '角色授权',
                     'columns': {'role_id': '角色ID',
                                 'resource_id': '资源ID',
                                 'level': '授权级别',
                                 'updated_by': '更新人ID',
                                 'updated_at': '更新时间'}},
 'iam_sessions': {'comment': '登录会话',
                  'columns': {'id': '主键',
                              'user_id': '用户ID',
                              'family_id': '会话族ID',
                              'created_at': '创建时间',
                              'expires_at': '过期时间',
                              'revoked_at': '撤销时间',
                              'last_seen_at': '最近活跃时间',
                              'client_info': '客户端信息'}},
 'iam_user_roles': {'comment': '用户角色关系',
                    'columns': {'user_id': '用户ID',
                                'role_id': '角色ID',
                                'granted_by': '授权人ID',
                                'created_at': '授权时间'}},
 'iam_refresh_tokens': {'comment': '刷新令牌',
                        'columns': {'id': '主键',
                                    'session_id': '会话ID',
                                    'token_hash': '令牌哈希',
                                    'issued_at': '签发时间',
                                    'expires_at': '过期时间',
                                    'consumed_at': '消费时间',
                                    'replaced_by': '替换令牌ID'}}}


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
