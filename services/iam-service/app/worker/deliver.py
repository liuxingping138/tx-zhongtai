from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
from platform_common.logging_setup import get_logger

from app.application.event_map import map_outbox_to_ingest
from app.application.outbox_policy import next_retry_delay, next_status
from app.core.clock import utcnow
from app.core.config import Settings
from app.core.database import SessionLocal
from app.domain.models import OutboxEvent
from app.repositories import outbox as outbox_repo

logger = get_logger("iam.worker")


class DeliveryCounters:
    delivered = 0
    duplicate = 0
    retried = 0
    parked = 0
    lease_lost = 0


async def claim_and_deliver(settings: Settings, client: httpx.AsyncClient) -> int:
    async with SessionLocal() as session:
        events = await outbox_repo.claim_batch(
            session,
            limit=settings.worker_batch_size,
            lease=timedelta(seconds=settings.worker_lease_seconds),
        )
        await session.commit()
    for event in events:
        await _deliver_one(settings, client, event)
    return len(events)


async def _deliver_one(settings: Settings, client: httpx.AsyncClient, event: OutboxEvent) -> None:
    expected_lease = event.lease_until
    if expected_lease is None:
        logger.warning("outbox_missing_lease", event_id=str(event.event_id))
        return
    body = map_outbox_to_ingest(event)
    try:
        response = await client.post(
            "/internal/v1/audit/events",
            json=body,
            headers={
                "X-Internal-Service": "iam-service",
                "X-Internal-Token": settings.audit_ingest_secret,
            },
        )
    except httpx.HTTPError as exc:
        await _mark_failure(
            settings,
            event.event_id,
            expected_lease,
            event.attempts,
            f"network:{exc.__class__.__name__}",
        )
        return

    if response.status_code < 300:
        data = _json_data(response)
        async with SessionLocal() as session:
            ok = await outbox_repo.mark_delivered(session, event.event_id, expected_lease)
            await session.commit()
        if ok:
            DeliveryCounters.delivered += 1
            if data.get("duplicate"):
                DeliveryCounters.duplicate += 1
        else:
            DeliveryCounters.lease_lost += 1
            logger.warning("outbox_lease_lost", event_id=str(event.event_id), phase="delivered")
        return

    if response.status_code in {401, 403}:
        await _mark_failure(
            settings,
            event.event_id,
            expected_lease,
            settings.worker_max_attempts,
            f"http:{response.status_code}",
        )
        return
    await _mark_failure(settings, event.event_id, expected_lease, event.attempts, f"http:{response.status_code}")


def _json_data(response: httpx.Response) -> dict[str, Any]:
    try:
        raw = response.json()
    except ValueError:
        return {}
    payload = raw.get("data") if isinstance(raw, dict) else None
    return payload if isinstance(payload, dict) else {}


async def _mark_failure(
    settings: Settings,
    event_id: Any,
    expected_lease: Any,
    attempts: int,
    error_message: str,
) -> None:
    status = next_status(attempts=attempts, max_attempts=settings.worker_max_attempts)
    retry_at = None
    if status != "dead":
        retry_at = utcnow() + next_retry_delay(
            attempts=attempts,
            base_seconds=settings.worker_backoff_base_seconds,
            cap_seconds=settings.worker_backoff_cap_seconds,
        )
    async with SessionLocal() as session:
        ok = await outbox_repo.mark_retry(
            session,
            event_id,
            expected_lease,
            status=status,
            next_retry_at=retry_at,
            error_message=error_message,
        )
        await session.commit()
    if not ok:
        DeliveryCounters.lease_lost += 1
        logger.warning("outbox_lease_lost", event_id=str(event_id), phase="retry")
        return
    if status == "dead":
        DeliveryCounters.parked += 1
        logger.error("outbox_parked", event_id=str(event_id), error=error_message, attempts=attempts)
    else:
        DeliveryCounters.retried += 1
        logger.warning("outbox_retry", event_id=str(event_id), error=error_message, attempts=attempts)
