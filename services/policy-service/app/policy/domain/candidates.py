"""新增场景候选：AI 解读写出的、码表里还没有的场景，按「第一个新出现的那一级」归成一个候选，人对候选做决定。

决定（采纳 / 合并 / 驳回）记在候选上，候选的 key 就是规则：以后 AI 再写出同样的说法，归到同一个候选，
直接按已有决定处理，不再进待审。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from platform_common.orm_base import Base
from sqlalchemy import DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.policy.domain.fields import (
    SCENARIO_STATE_ADOPTED,
    SCENARIO_STATE_MERGED,
    SCENARIO_STATE_PENDING,
    SCENARIO_STATE_REJECTED,
)

STATUS_PENDING = "待审"
STATUS_ADOPTED = "已采纳"
STATUS_MERGED = "已合并"
STATUS_REJECTED = "已驳回"
STATUS_CHOICES: tuple[str, ...] = (STATUS_PENDING, STATUS_ADOPTED, STATUS_MERGED, STATUS_REJECTED)
# 候选的决定对应到解读行的场景状态
ROW_STATE_BY_STATUS = {
    STATUS_PENDING: SCENARIO_STATE_PENDING,
    STATUS_ADOPTED: SCENARIO_STATE_ADOPTED,
    STATUS_MERGED: SCENARIO_STATE_MERGED,
    STATUS_REJECTED: SCENARIO_STATE_REJECTED,
}

KIND_NEW = "新场景"
KIND_ASSOCIATION = "新关联"
# 新增级别：新场景按第一个新出现的那一级；新关联是各级场景码表里都有，只是没挂在这个行业下
LEVEL_LABELS = {1: "一级", 2: "二级", 3: "三级"}
LEVEL_ASSOCIATION = "新关联"
LEVEL_CHOICES: tuple[str, ...] = (*LEVEL_LABELS.values(), LEVEL_ASSOCIATION)

REJECT_REASONS: tuple[str, ...] = ("不是信息化场景", "太细，属于已有场景的一部分", "说法不对", "其他")

PATH_SEP = ">"
Names = tuple[str, str, str]


def _joined(names: tuple[str, ...]) -> str:
    return PATH_SEP.join(name for name in names if name)


def candidate_key(kind: str, industry: Names, scenario: Names, new_level: int) -> str:
    """候选的身份。新场景只看场景路径到新的那一级（各级场景号不分行业）；新关联连同行业一起算。"""

    if kind == KIND_NEW:
        return f"新|{_joined(scenario[:new_level])}"
    return f"关联|{'/'.join(name for name in industry if name)}|{_joined(scenario)}"


def candidate_path(kind: str, scenario: Names, new_level: int) -> Names:
    """候选自己的场景路径：新场景截到新的那一级，后面的下级算它的下级新场景。"""

    if kind != KIND_NEW:
        return scenario
    kept = [*scenario[:new_level], "", "", ""]
    return kept[0], kept[1], kept[2]


def level_label(kind: str, new_level: int) -> str:
    return LEVEL_LABELS.get(new_level, "") if kind == KIND_NEW else LEVEL_ASSOCIATION


def renamed_path(scenario: Names, new_level: int, name: str) -> Names:
    """采纳时改了新场景的名称：只换新的那一级，上级和下级不动。"""

    names = list(scenario)
    names[new_level - 1] = name
    return names[0], names[1], names[2]


class ScenarioCandidate(Base):
    __tablename__ = "policy_scenario_candidates"
    __table_args__ = (
        UniqueConstraint("key", name="uq_policy_scenario_candidates_key"),
        # 列表默认按状态分页签、政策数从多到少排
        Index("ix_policy_scenario_candidates_status_policies", "status", "policy_count", "id"),
        {"comment": "新增场景候选"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, comment="主键")
    key: Mapped[str] = mapped_column(Text, nullable=False, comment="候选标识（规则）")
    kind: Mapped[str] = mapped_column(String(16), nullable=False, comment="类型")
    new_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="新增的级别")
    level_label: Mapped[str] = mapped_column(String(16), nullable=False, comment="新增级别")
    scenario_l1: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="一级场景")
    scenario_l2: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="二级场景")
    scenario_l3: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="三级场景")
    industry_l1: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="一级行业（新关联）")
    industry_l2: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="二级行业（新关联）")
    industry_l3: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="三级行业（新关联）")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_PENDING, server_default=STATUS_PENDING, comment="状态"
    )
    adopted_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="采纳时改的名称")
    target_l1: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="合并到的一级场景")
    target_l2: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="合并到的二级场景")
    target_l3: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="合并到的三级场景")
    reject_reason: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="驳回原因")
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="决定说明")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="决定时间")
    decided_by_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="决定人ID")
    decided_by_name: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="决定人")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="解读行数")
    policy_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="政策数")
    industry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="涉及一级行业数")
    main_industry: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="主要一级行业")
    sample_title: Mapped[str] = mapped_column(String(500), nullable=False, default="", comment="最近一条来源政策")
    similar_name: Mapped[str] = mapped_column(String(800), nullable=False, default="", comment="最像的已有场景")
    similar_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="相似度")
    similar_level: Mapped[str] = mapped_column(String(8), nullable=False, default="", comment="码表相似")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="首次出现")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="最近出现")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")

    def path(self) -> Names:
        return self.scenario_l1, self.scenario_l2, self.scenario_l3

    def target(self) -> Names:
        return self.target_l1, self.target_l2, self.target_l3

    def row_state(self) -> str:
        return ROW_STATE_BY_STATUS[self.status]
