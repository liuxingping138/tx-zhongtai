"""本服务的审计事件映射与投递绑定。机制在 platform_common.audit_emit。

对话和试发的内容不进审计：提示词里常有业务数据，日志只记谁对哪个模板、哪个任务做了什么。
"""

from __future__ import annotations

from typing import Any

from platform_common.actors import Actor
from platform_common.audit_emit import AuditEmitter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domain.models import OutboxEvent

# 事件类型 -> (模块编码, 动作编码, 目标类型, 中文标签)
_EVENT_META = {
    "ai.prompt.created": ("ai.prompts", "create", "prompt_template", "新增提示词模板"),
    "ai.prompt.updated": ("ai.prompts", "update", "prompt_template", "编辑提示词模板"),
    "ai.prompt.deleted": ("ai.prompts", "delete", "prompt_template", "删除提示词模板"),
    "ai.prompt.file_uploaded": ("ai.prompts", "update", "prompt_template", "上传模板文件"),
    "ai.prompt.file_deleted": ("ai.prompts", "update", "prompt_template", "删除模板文件"),
    "ai.prompt.file_exported": ("ai.prompts", "export", "prompt_template", "下载模板文件"),
    "ai.prompt.released": ("ai.releases", "publish", "prompt_template", "模板上线"),
    "ai.prompt.offlined": ("ai.releases", "publish", "prompt_template", "模板下线"),
    "ai.prompt.sample_started": ("ai.prompts", "ask", "prompt_template", "样本试跑"),
    "ai.prompt.sample_stopped": ("ai.prompts", "ask", "prompt_template", "停止样本试跑"),
    "ai.prompt.sample_retried": ("ai.prompts", "ask", "prompt_template", "重跑样本试跑失败行"),
    "ai.prompt.sample_exported": ("ai.prompts", "export", "prompt_template", "下载样本试跑结果"),
    "ai.model.created": ("ai.models", "create", "ai_model", "新增模型配置"),
    "ai.model.updated": ("ai.models", "update", "ai_model", "编辑模型配置"),
    "ai.batch_run.started": ("ai.batch_runs", "run", "batch_run", "发起批量任务"),
    "ai.batch_run.stopped": ("ai.batch_runs", "stop", "batch_run", "停止批量任务"),
    "ai.batch_run.retried": ("ai.batch_runs", "run", "batch_run", "重跑批量任务失败行"),
    "ai.batch_run.deleted": ("ai.batch_runs", "delete", "batch_run", "删除批量任务记录"),
    "ai.batch_run.exported": ("ai.batch_runs", "export", "batch_run", "下载批量任务结果"),
}

_emitter = AuditEmitter(
    service_name="ai-service",
    event_meta=_EVENT_META,
    outbox_model=OutboxEvent,
    session_factory=SessionLocal,
    get_settings=get_settings,
)


async def enqueue_event(  # noqa: PLR0913  与公共 enqueue_event 同一组关键字参数，只多一个 category
    session: AsyncSession,
    *,
    event_type: str,
    actor: Actor,
    category: str | None = None,
    target_id: str | None = None,
    changes: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """category 是模板类型（policy / customer / tender）：操作日志的「类型」列据此显示政策、客户、招投标。
    模型配置这类不属于哪条业务线的不传。"""

    if category:
        extra = {**(extra or {}), "category": category}
    await _emitter.enqueue_event(
        session, event_type=event_type, actor=actor, target_id=target_id, changes=changes, extra=extra
    )


deliver_pending = _emitter.deliver_pending
outbox_loop = _emitter.outbox_loop


async def audit_template(
    session: AsyncSession, event_type: str, actor: Actor, template: Any, changes: dict[str, Any] | None = None
) -> None:
    """模板（PromptTemplate）的审计事件：带上模板类型，目标是模板ID。"""

    await enqueue_event(
        session, event_type=event_type, actor=actor, category=template.category, target_id=template.id, changes=changes
    )
