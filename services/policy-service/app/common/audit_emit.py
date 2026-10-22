"""本服务的审计事件映射与投递绑定。机制在 platform_common.audit_emit。"""

from __future__ import annotations

from platform_common.audit_emit import AuditEmitter

from app.common.models import OutboxEvent
from app.core.config import get_settings
from app.core.database import SessionLocal

# 事件类型 -> (模块编码, 动作编码, 目标类型, 中文标签)
_EVENT_META = {
    "scheduler.updated": ("system.scheduler", "update", "scheduled_job", "修改每日同步计划"),
    "scheduler.triggered": ("system.scheduler", "execute", "scheduled_job", "手动执行定时任务"),
    "policy.ai_tagging.config_updated": ("system.scheduler", "update", "scheduled_job", "修改政策 AI 打标设置"),
    "policy.ai_tagging.tagged": ("policy.base_tags", "import", "base_tag", "政策 AI 打标写入基础标签"),
    "policy.source.created": ("policy.sources", "create", "source", "新增信源"),
    "policy.source.updated": ("policy.sources", "update", "source", "编辑信源"),
    "policy.source.imported": ("policy.sources", "import", "source", "导入信源"),
    "policy.source.exported": ("policy.sources", "export", "source", "导出信源"),
    "policy.source.purged": ("policy.sources", "purge", "source", "清空信源表"),
    "policy.base_tag.created": ("policy.base_tags", "create", "base_tag", "新增政策基础标签"),
    "policy.base_tag.updated": ("policy.base_tags", "update", "base_tag", "编辑政策基础标签"),
    "policy.base_tag.imported": ("policy.base_tags", "import", "base_tag", "导入政策基础标签表"),
    "policy.base_tag.exported": ("policy.base_tags", "export", "base_tag", "导出政策基础标签表"),
    "policy.interpretation.created": ("policy.interpretations", "create", "interpretation", "新增政策解读"),
    "policy.interpretation.updated": ("policy.interpretations", "update", "interpretation", "编辑政策解读"),
    "policy.interpretation.imported": ("policy.interpretations", "import", "interpretation", "导入政策解读表"),
    "policy.interpretation.exported": ("policy.interpretations", "export", "interpretation", "导出政策解读表"),
    "policy.crawler_monitoring.exported": (
        "policy.crawler_monitoring",
        "export",
        "crawler_site",
        "导出爬虫监测",
    ),
}

_emitter = AuditEmitter(
    service_name="policy-service",
    event_meta=_EVENT_META,
    outbox_model=OutboxEvent,
    session_factory=SessionLocal,
    get_settings=get_settings,
)

enqueue_event = _emitter.enqueue_event
deliver_pending = _emitter.deliver_pending
outbox_loop = _emitter.outbox_loop
