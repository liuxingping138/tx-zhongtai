"""新增场景按场景审核：候选表，解读行加场景状态和所属候选

原来 AI 解读出的新增场景要逐行标人工验证、再点「同步新增场景」写进码表，几十万行时做不完，近义说法还会各占一个编号。
改成系统先和码表比对，把新的说法归成候选，人对候选做一次决定（采纳 / 合并 / 驳回），决定记成规则自动套用到以后的行。

解读表已有数据：新列带默认值（PostgreSQL 不重写表），索引用 CONCURRENTLY 建，不锁写入。旧的「待同步」部分索引删掉。
已有的行场景状态为空，上线后在 policy-worker 里跑 `python -m app.cli.classify_scenarios` 补比对。
表和列的说明写死在这里，不引用运行时的模型。

Revision ID: a2b3c4d5e6f9
Revises: f1a2b3c4d5e8
Create Date: 2026-11-02
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a2b3c4d5e6f9"
down_revision: Union[str, None] = "f1a2b3c4d5e8"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None

# (索引名, 表, 列, 部分索引条件, 中文说明)
INDEXES = (
    (
        "ix_policy_interpretations_unclassified",
        "policy_interpretations",
        "id",
        "scenario_state = ''",
        "还没和行业场景码表比对过的解读行",
    ),
    ("ix_policy_interpretations_scenario_state", "policy_interpretations", "scenario_state", "", "场景状态筛选"),
    ("ix_policy_interpretations_candidate_id", "policy_interpretations", "candidate_id", "", "按新增场景候选取解读行"),
)
# 换成候选之后不再用的索引
DROPPED = (
    (
        "ix_policy_interpretations_unsynced_scenarios",
        "policy_interpretations",
        "updated_at, id",
        "is_new_scenario = '是' AND data_status = '人工验证' AND scenario_synced_at IS NULL",
        "人工验证过、还没同步进码表的新增场景",
    ),
)


def _text(name: str, length: int, comment: str) -> sa.Column:
    return sa.Column(name, sa.String(length), nullable=False, server_default="", comment=comment)


def upgrade() -> None:
    op.create_table(
        "policy_scenario_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, comment="主键"),
        sa.Column("key", sa.Text(), nullable=False, comment="候选标识（规则）"),
        sa.Column("kind", sa.String(16), nullable=False, comment="类型"),
        sa.Column("new_level", sa.Integer(), nullable=False, server_default="0", comment="新增的级别"),
        sa.Column("level_label", sa.String(16), nullable=False, comment="新增级别"),
        _text("scenario_l1", 255, "一级场景"),
        _text("scenario_l2", 255, "二级场景"),
        _text("scenario_l3", 255, "三级场景"),
        _text("industry_l1", 128, "一级行业（新关联）"),
        _text("industry_l2", 128, "二级行业（新关联）"),
        _text("industry_l3", 128, "三级行业（新关联）"),
        sa.Column("status", sa.String(16), nullable=False, server_default="待审", comment="状态"),
        _text("adopted_name", 255, "采纳时改的名称"),
        _text("target_l1", 255, "合并到的一级场景"),
        _text("target_l2", 255, "合并到的二级场景"),
        _text("target_l3", 255, "合并到的三级场景"),
        _text("reject_reason", 64, "驳回原因"),
        sa.Column("note", sa.Text(), nullable=False, server_default="", comment="决定说明"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True, comment="决定时间"),
        _text("decided_by_id", 64, "决定人ID"),
        _text("decided_by_name", 128, "决定人"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0", comment="解读行数"),
        sa.Column("policy_count", sa.Integer(), nullable=False, server_default="0", comment="政策数"),
        sa.Column("industry_count", sa.Integer(), nullable=False, server_default="0", comment="涉及一级行业数"),
        _text("main_industry", 128, "主要一级行业"),
        _text("sample_title", 500, "最近一条来源政策"),
        _text("similar_name", 800, "最像的已有场景"),
        sa.Column("similar_score", sa.Float(), nullable=False, server_default="0", comment="相似度"),
        _text("similar_level", 8, "码表相似"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, comment="首次出现"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, comment="最近出现"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1", comment="版本号"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, comment="更新时间"),
        sa.UniqueConstraint("key", name="uq_policy_scenario_candidates_key"),
        comment="新增场景候选",
    )
    op.create_index(
        "ix_policy_scenario_candidates_status_policies",
        "policy_scenario_candidates",
        ["status", "policy_count", "id"],
    )
    op.add_column(
        "policy_interpretations",
        sa.Column("scenario_state", sa.String(16), nullable=False, server_default="", comment="场景状态"),
    )
    op.add_column(
        "policy_interpretations",
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=True, comment="新增场景候选ID"),
    )
    with op.get_context().autocommit_block():
        for name, *_ in DROPPED:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        for name, table, columns, where, comment in INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
            predicate = f" WHERE {where}" if where else ""
            op.execute(f"CREATE INDEX CONCURRENTLY {name} ON {table} ({columns}){predicate}")
            op.execute(f"COMMENT ON INDEX {name} IS '{comment}'")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, *_ in reversed(INDEXES):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
        for name, table, columns, where, comment in DROPPED:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({columns}) WHERE {where}")
            op.execute(f"COMMENT ON INDEX {name} IS '{comment}'")
    op.drop_column("policy_interpretations", "candidate_id")
    op.drop_column("policy_interpretations", "scenario_state")
    op.drop_index("ix_policy_scenario_candidates_status_policies", table_name="policy_scenario_candidates")
    op.drop_table("policy_scenario_candidates")
