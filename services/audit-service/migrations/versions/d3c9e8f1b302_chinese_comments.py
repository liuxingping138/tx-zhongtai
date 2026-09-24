"""add chinese table and column comments

Revision ID: d3c9e8f1b302
Revises: c2b8d4e7a201
Create Date: 2026-09-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d3c9e8f1b302"
down_revision: Union[str, None] = "c2b8d4e7a201"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


# 冻结此修订当时的表/列。历史迁移不能导入运行时模型：模型以后新增的列在这一步还不存在，
# 空库从头迁移会报 column does not exist（codebook 同类迁移 2026-09-24 已踩到）。
COMMENTS = {'audit_events': {'comment': '操作日志',
                  'columns': {'id': '主键',
                              'event_id': '业务事件ID',
                              'occurred_at': '发生时间',
                              'received_at': '接收时间',
                              'source_service': '来源服务',
                              'schema_version': '事件结构版本',
                              'trace_id': '链路追踪ID',
                              'request_id': '请求ID',
                              'actor_id': '操作人ID',
                              'actor_name_snapshot': '操作人姓名',
                              'module_code': '模块编码',
                              'action_code': '动作编码',
                              'target_type': '对象类型',
                              'target_id': '对象ID',
                              'outcome': '结果',
                              'error_code': '错误码',
                              'client_ip': '客户端IP',
                              'user_agent': '浏览器标识',
                              'changes': '变更内容',
                              'summary': '摘要',
                              'duration_ms': '耗时毫秒'}}}


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
