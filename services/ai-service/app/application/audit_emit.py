"""本服务的审计事件映射与投递绑定。机制在 platform_common.audit_emit。

对话和试发的内容不进审计：提示词里常有业务数据，日志只记谁对哪个模板、哪个任务做了什么。
"""

from __future__ import annotations

from platform_common.audit_emit import AuditEmitter

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

enqueue_event = _emitter.enqueue_event
deliver_pending = _emitter.deliver_pending
outbox_loop = _emitter.outbox_loop
