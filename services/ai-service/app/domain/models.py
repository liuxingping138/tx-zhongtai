"""AI提问的表结构。主键沿用旧系统的 32 位十六进制 ID，迁移过来的模板和历史保持原 ID。"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from platform_common.orm_base import Base
from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.categories import DEFAULT_CATEGORY


def new_id() -> str:
    return uuid.uuid4().hex


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# 批量任务状态：排队 → 运行 → (停止中) → 完成/失败/已停止/中断
RUN_QUEUED = "queued"
RUN_RUNNING = "running"
RUN_STOPPING = "stopping"
RUN_DONE = "done"
RUN_FAILED = "failed"
RUN_CANCELLED = "cancelled"
RUN_INTERRUPTED = "interrupted"
ACTIVE_STATUSES = (RUN_QUEUED, RUN_RUNNING, RUN_STOPPING)
# 发起来源：批量任务页（manual）、政策定时打标（pipeline）都跑上线版本；样本试跑（sample）跑草稿和模板的测试样本，
# 只在模板页看，不进批量任务列表。
RUN_SOURCE_MANUAL = "manual"
RUN_SOURCE_PIPELINE = "pipeline"
RUN_SOURCE_SAMPLE = "sample"


class PromptTemplate(Base):
    __tablename__ = "ai_prompt_templates"
    __table_args__ = {"comment": "提示词模板"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id, comment="模板ID")
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="提示词标题")
    category: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DEFAULT_CATEGORY, server_default=DEFAULT_CATEGORY, comment="模板类型"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="提示词内容")
    output_fields: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="新增输出字段")
    model_id: Mapped[str] = mapped_column(String(100), nullable=False, default="", comment="模型ID")
    excel_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="Excel 文件名")
    excel_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="Excel 数据行数")
    excel_headers: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, comment="Excel 表头")
    code_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="码表文件名")
    # 选了系统码表就不用上传的码表文件，每次实时从码表服务取。
    code_table: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", server_default="", comment="系统码表"
    )
    release_id: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="当前上线版本ID")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间")
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="创建人ID")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="创建人")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")
    updated_by_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="更新人ID")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="更新人")


class TemplateRelease(Base):
    """模板上线时冻结的一版。定时任务只跑上线版本：之后再改模板只改草稿，重新上线才生效。"""

    __tablename__ = "ai_template_releases"
    __table_args__ = {"comment": "模板上线版本"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id, comment="版本ID")
    prompt_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="模板ID")
    release_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="上线版本号")
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="提示词标题")
    category: Mapped[str] = mapped_column(String(16), nullable=False, comment="模板类型")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="提示词内容")
    output_fields: Mapped[str] = mapped_column(Text, nullable=False, comment="新增输出字段")
    model_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="模型ID")
    code_table: Mapped[str] = mapped_column(String(32), nullable=False, default="", comment="系统码表")
    code_name: Mapped[str] = mapped_column(String(255), nullable=False, default="", comment="码表文件名")
    released_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="上线时间")
    released_by_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="上线人ID")
    released_by_name: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="上线人")


class AiModel(Base):
    """可选的大模型，在「模型配置」页维护。模板和任务按 id 引用，所以不删只停用。

    参数含义和计费规则见 app.domain.llm_models；密钥不在这里，按厂商放在服务环境变量里。
    """

    __tablename__ = "ai_models"
    __table_args__ = {"comment": "大模型配置"}

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="模型ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="显示名称")
    provider: Mapped[str] = mapped_column(String(16), nullable=False, comment="厂商")
    endpoint: Mapped[str] = mapped_column(String(128), nullable=False, comment="接入点")
    web_search: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="联网搜索")
    thinking: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="深度思考")
    reasoning_effort: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="思考强度")
    service_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="", comment="服务档位")
    input_price: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, comment="常规输入单价(元/千token)")
    output_price: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, comment="常规输出单价(元/千token)")
    flex_input_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True, comment="低优输入单价(元/千token)"
    )
    flex_output_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True, comment="低优输出单价(元/千token)"
    )
    peak_input_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True, comment="高峰输入单价(元/千token)"
    )
    peak_output_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True, comment="高峰输出单价(元/千token)"
    )
    peak_hours: Mapped[str] = mapped_column(String(100), nullable=False, default="", comment="高峰时段")
    search_price: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, comment="联网单价(元/次)")
    rate_limit: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="限流说明")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="创建人")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")
    updated_by_name: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="更新人")


class BatchRun(Base):
    """模板内容、输出字段在发起时冻结成快照：之后改模板不影响历史，模板删了也能追溯。"""

    __tablename__ = "ai_batch_runs"
    __table_args__ = {"comment": "批量任务（含定时任务和样本试跑）"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id, comment="任务ID")
    prompt_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="模板ID")
    prompt_title: Mapped[str] = mapped_column(String(255), nullable=False, comment="提问标题")
    prompt_category: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DEFAULT_CATEGORY, server_default=DEFAULT_CATEGORY, comment="模板类型"
    )
    prompt_content: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="提问模板内容")
    output_fields: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="解析字段快照")
    model_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="模型ID")
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="模型名称")
    thinking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="深度思考")
    row_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="运行条数上限")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=RUN_QUEUED, index=True, comment="运行状态")
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="总条数")
    done_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="已处理条数")
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="失败条数")
    format_failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", comment="格式不对条数"
    )
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="输入token")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="输出token")
    search_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="联网次数")
    inference_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal(0), comment="推理费用(元)"
    )
    search_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal(0), comment="联网费用(元)"
    )
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="请求停止")
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="心跳时间")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="错误信息")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="结束时间")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True, comment="发起时间"
    )
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="发起人ID")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="发起人")
    # 流水线（政策服务定时打标）发起的任务按低优档跑，并带费用上限。
    source: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=RUN_SOURCE_MANUAL,
        server_default=RUN_SOURCE_MANUAL,
        index=True,
        comment="发起来源",
    )
    release_no: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="上线版本号")
    # 跑模板草稿时记下那次保存的时间（批量任务可以不等上线）；跑上线版本时为空，看上线版本号。
    draft_saved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="草稿保存时间"
    )
    input_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default="", comment="输入文件名"
    )
    service_tier: Mapped[str] = mapped_column(
        String(16), nullable=False, default="", server_default="", comment="服务档位"
    )
    cost_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True, comment="费用上限(元)")


# 试发、多轮对话一次调用记一行（批量任务的费用记在 BatchRun 上），费用账单把两边合起来。
CALL_TRIAL = "trial"
CALL_CHAT = "chat"


class CallUsage(Base):
    """一次试发或多轮对话的用量和费用。只记谁在什么时候用哪个模型花了多少，不记提问和回答内容。"""

    __tablename__ = "ai_call_usages"
    __table_args__ = {"comment": "试发和多轮对话用量"}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id, comment="记录ID")
    kind: Mapped[str] = mapped_column(String(16), nullable=False, comment="调用类型")
    model_id: Mapped[str] = mapped_column(String(100), nullable=False, comment="模型ID")
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="模型名称")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="输入token")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="输出token")
    search_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="联网次数")
    inference_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal(0), comment="推理费用(元)"
    )
    search_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal(0), comment="联网费用(元)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True, comment="调用时间"
    )
    created_by_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", comment="调用人ID")
    created_by_name: Mapped[str] = mapped_column(String(128), nullable=False, default="", comment="调用人")


class WorkerHeartbeat(Base):
    __tablename__ = "ai_worker_heartbeat"
    __table_args__ = {"comment": "批量执行进程心跳"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="主键")
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="最近心跳时间")


class OutboxEvent(Base):
    __tablename__ = "ai_outbox"
    __table_args__ = {"comment": "AI提问服务出站事件"}

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="事件ID")
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, comment="事件类型")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="事件结构版本")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, comment="事件内容")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True, comment="投递状态")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="重试次数")
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, comment="下次重试时间"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="租约截止时间")
