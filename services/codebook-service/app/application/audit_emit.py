"""本服务的审计事件映射与投递绑定。机制在 platform_common.audit_emit。"""

from __future__ import annotations

from platform_common.audit_emit import AuditEmitter

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domain.models import OutboxEvent

# 事件类型 -> (模块编码, 动作编码, 目标类型, 中文标签)
_EVENT_META = {
    "codebook.policy_type.created": ("codebook.policy_types", "create", "policy_type", "新增政策类型"),
    "codebook.policy_type.updated": ("codebook.policy_types", "update", "policy_type", "编辑政策类型"),
    "codebook.policy_type.imported": ("codebook.policy_types", "import", "policy_type", "导入政策类型码表"),
    "codebook.policy_type.exported": ("codebook.policy_types", "export", "policy_type", "导出政策类型码表"),
    "codebook.scenario.created": ("codebook.scenarios", "create", "scenario", "新增行业场景码表"),
    "codebook.scenario.updated": ("codebook.scenarios", "update", "scenario", "编辑行业场景码表"),
    "codebook.scenario.imported": ("codebook.scenarios", "import", "scenario", "导入行业场景码表"),
    "codebook.scenario.exported": ("codebook.scenarios", "export", "scenario", "导出行业场景码表"),
    "codebook.scenario.synced": ("codebook.scenarios", "import", "scenario", "政策解读新增场景同步进码表"),
    "codebook.scenario.renamed": ("codebook.scenarios", "update", "scenario", "新增场景审核里把已有场景改名"),
    "codebook.area_code.created": ("codebook.area_codes", "create", "area_code", "新增省市区编码"),
    "codebook.area_code.updated": ("codebook.area_codes", "update", "area_code", "编辑省市区编码"),
    "codebook.area_code.imported": ("codebook.area_codes", "import", "area_code", "导入省市区编码表"),
    "codebook.area_code.exported": ("codebook.area_codes", "export", "area_code", "导出省市区编码表"),
    "codebook.area_code.resolved": ("codebook.area_codes", "resolve", "area_code", "补全省市区编码"),
}

_emitter = AuditEmitter(
    service_name="codebook-service",
    event_meta=_EVENT_META,
    outbox_model=OutboxEvent,
    session_factory=SessionLocal,
    get_settings=get_settings,
)

enqueue_event = _emitter.enqueue_event
deliver_pending = _emitter.deliver_pending
outbox_loop = _emitter.outbox_loop
