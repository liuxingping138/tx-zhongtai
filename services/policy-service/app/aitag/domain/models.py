"""政策 AI 打标：配置（一行）和每次执行的批次记录。"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from platform_common.orm_base import Base
from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

CONFIG_ID = 1
DEFAULT_BATCH_SIZE = 1000
DEFAULT_CONTENT_MAX_CHARS = 15_000
DEFAULT_DAILY_COST_LIMIT = Decimal(100)


class PolicyAiConfig(Base):
    """只有一行。读取进度（采集日期 + 正文ID）也存在这里：一批全部写完才前移，中途失败下次从原处重读。"""

    __tablename__ = "policy_ai_config"
    __table_args__ = {"comment": "政策AI打标配置"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="固定记录编号")
    type_prompt_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="政策类型判断模板ID")
    interpret_prompt_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="政策解读模板ID")
    opportunity_prompt_id: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", comment="政策市场机会模板ID"
    )
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False, default=DEFAULT_BATCH_SIZE, comment="每批打标条数")
    content_max_chars: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_CONTENT_MAX_CHARS, comment="正文截取字数"
    )
    daily_cost_limit: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=DEFAULT_DAILY_COST_LIMIT, comment="每日费用上限(元)"
    )
    cursor_date: Mapped[date] = mapped_column(Date, nullable=False, comment="读取进度：采集日期")
    cursor_content_id: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", comment="读取进度：该日已读到的正文ID"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="更新时间")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="操作人")


class PolicyAiRun(Base):
    """一次执行（一批）。主键就是调度执行记录里的批次编号，调度页据此显示结果和费用。"""

    __tablename__ = "policy_ai_runs"
    __table_args__ = {"comment": "政策AI打标批次"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, comment="批次编号")
    status: Mapped[str] = mapped_column(String(16), nullable=False, comment="状态")
    stage: Mapped[str] = mapped_column(String(16), nullable=False, comment="进行到的步骤")
    source_from: Mapped[str] = mapped_column(String(240), nullable=False, default="", comment="读取起点")
    source_to: Mapped[str] = mapped_column(String(240), nullable=False, default="", comment="读取终点")
    source_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="读取条数")
    type_run_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="类型判断任务ID")
    tagged_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="写入基础标签条数")
    type_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="类型判断失败条数")
    interpret_run_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="政策解读任务ID")
    opportunity_run_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="市场机会任务ID")
    interpret_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="写入政策解读条数")
    interpret_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="解读失败条数")
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
    note: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="说明")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="失败原因")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="结束时间")
