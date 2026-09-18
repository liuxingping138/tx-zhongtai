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

logger = get_logger("codebook.audit")

_EVENT_META = {
    "codebook.policy_type.created": ("codebook.policy_types", "create", "policy_type", "新增政策类型"),
    "codebook.policy_type.updated": ("codebook.policy_types", "update", "policy_type", "编辑政策类型"),
    "codebook.policy_type.imported": ("codebook.policy_types", "import", "policy_type", "导入政策类型码表"),
    "codebook.policy_type.exported": ("codebook.policy_types", "export", "policy_type", "导出政策类型码表"),
    "codebook.scenario.created": ("codebook.scenarios", "create", "scenario", "新增场景码表"),
    "codebook.scenario.updated": ("codebook.scenarios", "update", "scenario", "编辑场景码表"),
    "codebook.scenario.imported": ("codebook.scenarios", "import", "scenario", "导入场景码表"),
    "codebook.scenario.exported": ("codebook.scenarios", "export", "scenario", "导出场景码表"),
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
        event.event_type, ("codebook", event.event_type, "record", event.event_type)
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
                            "X-Internal-Service": "codebook-service",
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
                    logger.warning("codebook_audit_deliver_failed", event_id=str(event.event_id))
    return delivered


async def outbox_loop(stop: asyncio.Event, settings: Settings) -> None:
    while not stop.is_set():
        try:
            await deliver_pending(settings)
        except Exception:  # noqa: BLE001
            logger.exception("codebook_outbox_loop_failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_interval_seconds)
        except TimeoutError:
            continue
