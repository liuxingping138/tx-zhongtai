from __future__ import annotations

import asyncio
from typing import Any

import httpx
from platform_common.logging_setup import get_logger
from platform_common.request_context import get_request_id
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.domain.models import OutboxEvent  # noqa: F401 used in _to_ingest
from app.repositories import outbox as outbox_repo

logger = get_logger("policy.audit")

_EVENT_META = {
    "policy.source.created": ("policy.sources", "create", "source", "新增信源"),
    "policy.source.updated": ("policy.sources", "update", "source", "编辑信源"),
    "policy.source.imported": ("policy.sources", "import", "source", "导入信源"),
    "policy.source.exported": ("policy.sources", "export", "source", "导出信源"),
    "policy.base_tag.created": ("policy.base_tags", "create", "base_tag", "新增政策基础标签"),
    "policy.base_tag.updated": ("policy.base_tags", "update", "base_tag", "编辑政策基础标签"),
    "policy.base_tag.imported": ("policy.base_tags", "import", "base_tag", "导入政策基础标签表"),
    "policy.base_tag.exported": ("policy.base_tags", "export", "base_tag", "导出政策基础标签表"),
    "policy.interpretation.created": ("policy.interpretations", "create", "interpretation", "新增政策解读"),
    "policy.interpretation.updated": ("policy.interpretations", "update", "interpretation", "编辑政策解读"),
    "policy.interpretation.imported": ("policy.interpretations", "import", "interpretation", "导入政策解读表"),
    "policy.interpretation.exported": ("policy.interpretations", "export", "interpretation", "导出政策解读表"),
}


async def enqueue_event(
    session: AsyncSession,
    *,
    event_type: str,
    actor_id: str,
    actor_name: str,
    target_id: str | None = None,
    changes: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "actor_id": actor_id,
        "actor_name": actor_name,
        "target_id": target_id,
        "outcome": "success",
        "request_id": get_request_id(),
        "changes": changes or {},
    }
    if extra:
        payload.update(extra)
    await outbox_repo.enqueue(session, event_type=event_type, payload=payload)


def _to_ingest(event: OutboxEvent) -> dict[str, Any]:
    payload = event.payload if isinstance(event.payload, dict) else {}
    module_code, action_code, target_type, label = _EVENT_META.get(
        event.event_type, ("policy", event.event_type, "record", event.event_type)
    )
    actor = payload.get("actor_name")
    target = payload.get("target_id")
    summary = [label]
    if actor:
        summary.append(str(actor))
    if target:
        summary.append(str(target))
    if payload.get("inserted") is not None:
        summary.append(f"新增{payload.get('inserted')}条")
    return {
        "event_id": str(event.event_id),
        "occurred_at": event.created_at.isoformat(),
        "schema_version": event.schema_version,
        "request_id": payload.get("request_id"),
        "actor_id": payload.get("actor_id"),
        "actor_name_snapshot": actor,
        "module_code": module_code,
        "action_code": action_code,
        "target_type": target_type,
        "target_id": None if target is None else str(target),
        "outcome": payload.get("outcome") or "success",
        "changes": payload.get("changes") or payload,
        "summary": " / ".join(str(item) for item in summary if item),
    }


async def deliver_pending(settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    async with SessionLocal() as session:
        events = await outbox_repo.claim_pending(session)
        await session.commit()
    if not events:
        return 0
    delivered = 0
    async with httpx.AsyncClient(base_url=settings.audit_ingest_url.rstrip("/"), timeout=5.0) as client:
        for event in events:
            async with SessionLocal() as session:
                try:
                    response = await client.post(
                        "/internal/v1/audit/events",
                        json=_to_ingest(event),
                        headers={
                            "X-Internal-Service": "policy-service",
                            "X-Internal-Token": settings.audit_ingest_secret,
                        },
                    )
                    row = await session.get(OutboxEvent, event.event_id)
                    if row is None:
                        continue
                    if response.status_code < 300:
                        await outbox_repo.mark_delivered(session, row)
                        delivered += 1
                    else:
                        await outbox_repo.mark_retry(
                            session,
                            row,
                            error=f"http:{response.status_code}",
                            max_attempts=settings.worker_max_attempts,
                        )
                    await session.commit()
                except httpx.HTTPError as exc:
                    row = await session.get(OutboxEvent, event.event_id)
                    if row is not None:
                        await outbox_repo.mark_retry(
                            session,
                            row,
                            error=f"network:{exc.__class__.__name__}",
                            max_attempts=settings.worker_max_attempts,
                        )
                        await session.commit()
                    logger.warning("policy_audit_deliver_failed", event_id=str(event.event_id))
    return delivered


async def outbox_loop(stop: asyncio.Event, settings: Settings) -> None:
    while not stop.is_set():
        try:
            await deliver_pending(settings)
        except Exception:  # noqa: BLE001
            logger.exception("policy_outbox_loop_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_interval_seconds)
        except TimeoutError:
            continue
