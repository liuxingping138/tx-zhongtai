"""智库服务审计事件映射与投递绑定。机制在 platform_common.audit_emit。"""

from __future__ import annotations

from platform_common.audit_emit import AuditEmitter

from app.common.models import OutboxEvent
from app.core.config import get_settings
from app.core.database import SessionLocal

# 事件类型 -> (模块编码, 动作编码, 目标类型, 中文标签)
_EVENT_META = {
    "thinktank.knowledge.created": ("thinktank.knowledge", "create", "knowledge_file", "上传知识文件"),
    "thinktank.knowledge.updated": ("thinktank.knowledge", "update", "knowledge_file", "编辑知识标签"),
    "thinktank.knowledge.deleted": ("thinktank.knowledge", "delete", "knowledge_file", "删除知识文件"),
    "thinktank.knowledge.upload_tags": ("thinktank.knowledge", "upload_tags", "knowledge_file", "上传知识标签"),
    "thinktank.knowledge.exported": ("thinktank.knowledge", "export", "knowledge_file", "导出知识列表"),
    "thinktank.knowledge.export_undefined": (
        "thinktank.knowledge",
        "export_undefined",
        "knowledge_file",
        "导出未定义数据",
    ),
    "thinktank.knowledge.previewed": ("thinktank.knowledge", "preview", "knowledge_file", "预览知识文件"),
    "thinktank.knowledge.favorited": ("thinktank.knowledge", "favorite", "knowledge_file", "收藏知识文件"),
    "thinktank.knowledge.unfavorited": ("thinktank.knowledge", "unfavorite", "knowledge_file", "取消收藏知识文件"),
    "thinktank.knowledge.downloaded": ("thinktank.knowledge", "download", "knowledge_file", "下载知识文件"),
    "thinktank.knowledge.access_denied": (
        "thinktank.knowledge",
        "access_denied",
        "knowledge_file",
        "越权访问知识文件",
    ),
}

_emitter = AuditEmitter(
    service_name="thinktank-service",
    event_meta=_EVENT_META,
    outbox_model=OutboxEvent,
    session_factory=SessionLocal,
    get_settings=get_settings,
)

enqueue_event = _emitter.enqueue_event
deliver_pending = _emitter.deliver_pending
outbox_loop = _emitter.outbox_loop
