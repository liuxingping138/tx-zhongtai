"""智库服务审计事件映射与投递绑定。机制在 platform_common.audit_emit。"""

from __future__ import annotations

from platform_common.audit_emit import AuditEmitter

from app.common.models import OutboxEvent
from app.core.config import get_settings
from app.core.database import SessionLocal

# 事件类型 -> (模块编码, 动作编码, 目标类型, 中文标签)
_EVENT_META = {
    "thinktank.knowledge.created": ("thinktank.knowledge", "create", "knowledge_file", "上传资料文件"),
    "thinktank.knowledge.updated": ("thinktank.knowledge", "update", "knowledge_file", "编辑资料标签"),
    "thinktank.knowledge.deleted": ("thinktank.knowledge", "delete", "knowledge_file", "删除资料文件"),
    "thinktank.knowledge.upload_tags": ("thinktank.knowledge", "upload_tags", "knowledge_file", "上传资料标签"),
    "thinktank.knowledge.exported": ("thinktank.knowledge", "export", "knowledge_file", "导出资料列表"),
    "thinktank.knowledge.export_undefined": (
        "thinktank.knowledge",
        "export_undefined",
        "knowledge_file",
        "导出未定义资料",
    ),
    "thinktank.knowledge.previewed": ("thinktank.knowledge", "preview", "knowledge_file", "预览资料文件"),
    "thinktank.knowledge.favorited": ("thinktank.knowledge", "favorite", "knowledge_file", "收藏资料文件"),
    "thinktank.knowledge.unfavorited": ("thinktank.knowledge", "unfavorite", "knowledge_file", "取消收藏资料文件"),
    "thinktank.knowledge.downloaded": ("thinktank.knowledge", "download", "knowledge_file", "下载资料文件"),
    "thinktank.knowledge.access_denied": (
        "thinktank.knowledge",
        "access_denied",
        "knowledge_file",
        "越权访问资料文件",
    ),
    "thinktank.reports.created": ("thinktank.reports", "create", "report_file", "上传报告文件"),
    "thinktank.reports.updated": ("thinktank.reports", "update", "report_file", "编辑报告标签"),
    "thinktank.reports.deleted": ("thinktank.reports", "delete", "report_file", "删除报告文件"),
    "thinktank.reports.upload_tags": ("thinktank.reports", "upload_tags", "report_file", "上传报告标签"),
    "thinktank.reports.exported": ("thinktank.reports", "export", "report_file", "导出报告列表"),
    "thinktank.reports.export_undefined": (
        "thinktank.reports",
        "export_undefined",
        "report_file",
        "导出未定义报告",
    ),
    "thinktank.reports.previewed": ("thinktank.reports", "preview", "report_file", "预览报告文件"),
    "thinktank.reports.favorited": ("thinktank.reports", "favorite", "report_file", "收藏报告文件"),
    "thinktank.reports.unfavorited": ("thinktank.reports", "unfavorite", "report_file", "取消收藏报告文件"),
    "thinktank.reports.downloaded": ("thinktank.reports", "download", "report_file", "下载报告文件"),
    "thinktank.proposals.created": ("thinktank.proposals", "create", "proposal_file", "上传方案文件"),
    "thinktank.proposals.updated": ("thinktank.proposals", "update", "proposal_file", "编辑方案标签"),
    "thinktank.proposals.deleted": ("thinktank.proposals", "delete", "proposal_file", "删除方案文件"),
    "thinktank.proposals.upload_tags": ("thinktank.proposals", "upload_tags", "proposal_file", "上传方案标签"),
    "thinktank.proposals.exported": ("thinktank.proposals", "export", "proposal_file", "导出方案列表"),
    "thinktank.proposals.export_undefined": (
        "thinktank.proposals",
        "export_undefined",
        "proposal_file",
        "导出未定义方案",
    ),
    "thinktank.proposals.previewed": ("thinktank.proposals", "preview", "proposal_file", "预览方案文件"),
    "thinktank.proposals.favorited": ("thinktank.proposals", "favorite", "proposal_file", "收藏方案文件"),
    "thinktank.proposals.unfavorited": ("thinktank.proposals", "unfavorite", "proposal_file", "取消收藏方案文件"),
    "thinktank.proposals.downloaded": ("thinktank.proposals", "download", "proposal_file", "下载方案文件"),
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
