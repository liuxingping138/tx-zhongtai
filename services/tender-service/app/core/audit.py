"""招中标导出审计直连上报（无独立库/Outbox，失败即中止导出）。"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from platform_common.actors import Actor
from platform_common.clock import utcnow
from platform_common.config import Environment
from platform_common.errors import DependencyUnavailableError
from platform_common.internal_calls import internal_headers
from platform_common.request_context import get_request_id

from app.core.config import get_settings


async def emit_export_audit(
    *,
    actor: Actor,
    kind: str,
    exported_rows: int,
    filters: dict[str, Any],
) -> None:
    settings = get_settings()
    if not settings.audit_ingest_secret:
        if settings.environment == Environment.PRODUCTION:
            raise DependencyUnavailableError("审计配置缺失，导出已中止")
        return
    payload = {
        "event_id": str(uuid.uuid4()),
        "occurred_at": utcnow().isoformat(),
        "schema_version": 1,
        "request_id": get_request_id(),
        "actor_id": actor.id,
        "actor_name_snapshot": actor.name,
        "module_code": f"tender.{kind}",
        "action_code": "export",
        "target_type": f"tender.{kind}",
        "outcome": "success",
        "changes": {"exported_rows": exported_rows, "filters": filters},
        "summary": f"导出招中标数据 {exported_rows} 条",
    }
    url = f"{settings.audit_ingest_url.rstrip('/')}/internal/v1/audit/events"
    headers = internal_headers("tender-service", settings.audit_ingest_secret)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload, headers=headers)
        if not response.is_success:
            raise DependencyUnavailableError("审计服务暂不可用，导出已中止")
    except httpx.HTTPError as exc:
        raise DependencyUnavailableError("审计服务暂不可用，导出已中止") from exc
