"""政策 AI 打标：三个任务的设置和每次执行的批次记录。"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from platform_common.orm_base import Base
from sqlalchemy import Date, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

DEFAULT_BATCH_SIZE = 1000
# 0 表示正文全文照传，不截断。
DEFAULT_CONTENT_MAX_CHARS = 0
DEFAULT_DAILY_COST_LIMIT = Decimal(100)


class PolicyAiTask(Base):
    """打标的三个任务各一行（见 domain.tasks.TASKS），各有模板、每批条数、正文长度和每日上限。

    读取进度（采集日期 + 正文ID）只有类型判断用：一批全部写完才前移，中途失败下次从原处重读。
    解读、市场机会按待办做，不需要进度。
    """

    __tablename__ = "policy_ai_tasks"
    __table_args__ = {"comment": "政策AI打标任务"}

    code: Mapped[str] = mapped_column(String(16), primary_key=True, comment="任务编码")
    prompt_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="使用的上线模板ID")
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False, default=DEFAULT_BATCH_SIZE, comment="每批条数")
    content_max_chars: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_CONTENT_MAX_CHARS, comment="正文截取字数（0 为全文）"
    )
    daily_cost_limit: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=DEFAULT_DAILY_COST_LIMIT, comment="每日费用上限(元)"
    )
    cursor_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="读取进度：采集日期（类型判断用）")
    cursor_content_id: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", comment="读取进度：该日已读到的正文ID"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="更新时间")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="操作人")


class PolicyAiRun(Base):
    """一次执行（一批），属于一个任务。主键就是调度执行记录里的批次编号，调度页据此显示结果和费用。

    拆成三个任务之前的批次三步一起跑，记在类型判断名下，各步费用仍在三列费用里。
    """

    __tablename__ = "policy_ai_runs"
    __table_args__ = (
        Index("ix_policy_ai_runs_started_at", "started_at"),
        # 每个任务「今日已花」、最近一批按任务和开始时间查。
        Index("ix_policy_ai_runs_task_started_at", "task", "started_at"),
        {"comment": "政策AI打标批次"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, comment="批次编号")
    task: Mapped[str] = mapped_column(String(16), nullable=False, default="type", comment="任务编码")
    status: Mapped[str] = mapped_column(String(16), nullable=False, comment="状态")
    stage: Mapped[str] = mapped_column(String(16), nullable=False, comment="进行到的步骤")
    source_from: Mapped[str] = mapped_column(String(240), nullable=False, default="", comment="读取起点")
    source_to: Mapped[str] = mapped_column(String(240), nullable=False, default="", comment="读取终点")
    source_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="本批处理的政策条数")
    type_run_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="类型判断任务ID")
    tagged_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="写入基础标签条数")
    type_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="类型判断失败条数")
    interpret_run_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="政策解读任务ID")
    opportunity_run_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="市场机会任务ID")
    interpret_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="写入政策解读条数")
    interpret_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="解读失败条数")
    opportunity_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="回填市场机会行数")
    opportunity_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="市场机会失败条数")
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal(0), comment="费用(元)")
    type_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal(0), comment="类型判断费用(元)"
    )
    interpret_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal(0), comment="政策解读费用(元)"
    )
    opportunity_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal(0), comment="市场机会费用(元)"
    )
    scenario_run_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="找相似场景任务ID")
    scenario_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="判断过的新增场景数")
    scenario_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="找相似失败数")
    scenario_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal(0), comment="找相似场景费用(元)"
    )
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="说明")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="失败原因")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="结束时间")


class SkippedSource(Base):
    """类型判断问过、但和已有基础标签内容一样所以没写进去的源政策（各地转发同一文件）。

    读取进度往回调重扫时，「打过类型标的跳过」只认基础标签，认不出这些，每次都重新付费再问一遍、又被跳过。
    """

    __tablename__ = "policy_ai_skipped_sources"
    __table_args__ = {"comment": "政策AI打标跳过的源政策"}

    source_content_id: Mapped[str] = mapped_column(String(200), primary_key=True, comment="源政策ID")
    reason: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="", comment="跳过原因")
    skipped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="跳过时间")
