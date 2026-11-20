"""招中标审计直连上报（无独立库/Outbox）：导出、查看正文都同步上报，失败即中止，不放出没留痕的数据。"""

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


async def _report(  # noqa: PLR0913  审计事件的几个字段都按关键字传
    actor: Actor,
    *,
    kind: str,
    action: str,
    changes: dict[str, Any],
    summary: str,
    refused: str,
    target_id: str | None = None,
) -> None:
    settings = get_settings()
    if not settings.audit_ingest_secret:
        if settings.environment == Environment.PRODUCTION:
            raise DependencyUnavailableError(f"审计配置缺失，{refused}")
        return
    payload = {
        "event_id": str(uuid.uuid4()),
        "occurred_at": utcnow().isoformat(),
        "schema_version": 1,
        "request_id": get_request_id(),
        "actor_id": actor.id,
        "actor_name_snapshot": actor.name,
        "module_code": f"tender.{kind}",
        "action_code": action,
        "target_type": f"tender.{kind}",
        "target_id": target_id,
        "outcome": "success",
        "changes": changes,
        "summary": summary,
    }
    url = f"{settings.audit_ingest_url.rstrip('/')}/internal/v1/audit/events"
    headers = internal_headers("tender-service", settings.audit_ingest_secret)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload, headers=headers)
        if not response.is_success:
            raise DependencyUnavailableError(f"审计服务暂不可用，{refused}")
    except httpx.HTTPError as exc:
        raise DependencyUnavailableError(f"审计服务暂不可用，{refused}") from exc


async def emit_export_audit(
    *,
    actor: Actor,
    kind: str,
    exported_rows: int,
    filters: dict[str, Any],
) -> None:
    await _report(
        actor,
        kind=kind,
        action="export",
        changes={"exported_rows": exported_rows, "filters": filters},
        summary=f"导出招中标数据 {exported_rows} 条",
        refused="导出已中止",
    )


async def emit_content_audit(*, actor: Actor, kind: str, record_id: int, project_status: str) -> None:
    """查看正文：正文是整篇标书，泄露时要查得到谁在什么时候看过哪条。"""

    await _report(
        actor,
        kind=kind,
        action="read",
        target_id=str(record_id),
        changes={"record_id": str(record_id), "project_status": project_status, "view": "content"},
        summary=f"查看招中标正文 {record_id}",
        refused="正文暂不能查看",
    )
