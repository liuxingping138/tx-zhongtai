"""爬虫配置同步的批次记录：统计页据此显示最近一次同步，调度页据此显示结果。"""

from __future__ import annotations

import uuid
from datetime import datetime

from platform_common.orm_base import Base
from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

# 调度任务编码。
JOB_CODE = "crawler_config"


class ConfigSyncRun(Base):
    """主键就是调度执行记录里的批次编号。"""

    __tablename__ = "policy_crawler_config_syncs"
    __table_args__ = (
        Index("ix_policy_crawler_config_syncs_started_at", "started_at"),
        {"comment": "爬虫配置同步批次"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, comment="批次编号")
    status: Mapped[str] = mapped_column(String(16), nullable=False, comment="状态")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="结束时间")
    rule_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="规则表栏目行数")
    rule_codes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="规则表网站编码数")
    blank_code_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="规则表没填网站编码的行数")
    matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="关联上的信源数")
    marked: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="本次标为已爬的信源数")
    redated: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="已爬但上线时间对齐成规则创建日期的信源数"
    )
    unknown_codes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="信源表里没有的网站编码数")
    added: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="本次按栏目展开新增的信源行数"
    )
    error_message: Mapped[str | None] = mapped_column(Text, comment="失败原因")
