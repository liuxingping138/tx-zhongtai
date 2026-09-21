"""业务事件入 Outbox、再投递到审计服务。

各业务服务的投递机制完全一致，只有事件映射表、服务名和 ORM model 不同，
所以这里参数化成 ``AuditEmitter``，服务内只保留自己的事件映射。

投递失败不丢事件：失败会回写 Outbox 并按指数退避重试，达到上限后置为 dead。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Any, Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_common.logging_setup import get_logger
from platform_common.outbox import OutboxRepository
from platform_common.redaction import redact
from platform_common.request_context import get_request_id

# 事件类型 -> (模块编码, 动作编码, 目标类型, 中文标签)
EventMeta = Mapping[str, tuple[str, str, str, str]]

# 导入导出类事件在摘要里追加的计数，按顺序拼接。
_SUMMARY_COUNTS: tuple[tuple[str, str], ...] = (
    ("inserted", "新增{}条"),
    ("deleted", "清空{}条"),
)


class _AuditSettings(Protocol):
    audit_ingest_url: str
    audit_ingest_secret: str
    worker_max_attempts: int
    worker_poll_interval_seconds: float


class AuditEmitter:
    def __init__(
        self,
        *,
        service_name: str,
        log_name: str,
        event_meta: EventMeta,
        default_module: str,
        outbox_model: type[Any],
        session_factory: async_sessionmaker[AsyncSession],
        get_settings: Callable[[], _AuditSettings],
    ) -> None:
        self._service_name = service_name
        self._event_meta = event_meta
        self._default_module = default_module
        self._model = outbox_model
        self._sessions = session_factory
        self._get_settings = get_settings
        self._repo = OutboxRepository(outbox_model)
        self._logger = get_logger(f"{log_name}.audit")
        self._log_name = log_name

    async def enqueue_event(
        self,
        session: AsyncSession,
        *,
        event_type: str,
        actor_id: str,
        actor_name: str,
        target_id: str | None = None,
        changes: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "actor_id": actor_id,
            "actor_name": actor_name,
            "target_id": target_id,
            "outcome": "success",
            "request_id": get_request_id(),
            "changes": changes or {},
        }
        if extra:
            payload.update(extra)
        # 入队即脱敏：Outbox 落在业务库里，投递成功前一直存着。
        # 这里收口后，敏感值不会因为某个调用方手滑而在业务库留痕。
        await self._repo.enqueue(session, event_type=event_type, payload=redact(payload))

    def to_ingest(self, event: Any) -> dict[str, Any]:
        payload = event.payload if isinstance(event.payload, dict) else {}
        module_code, action_code, target_type, label = self._event_meta.get(
            event.event_type,
            (self._default_module, event.event_type, "record", event.event_type),
        )
        actor = payload.get("actor_name")
        target = payload.get("target_id")
        summary = [label]
        if actor:
            summary.append(str(actor))
        if target:
            summary.append(str(target))
        for key, template in _SUMMARY_COUNTS:
            if payload.get(key) is not None:
                summary.append(template.format(payload.get(key)))
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

    async def deliver_pending(self, settings: _AuditSettings | None = None) -> int:
        settings = settings or self._get_settings()
        async with self._sessions() as session:
            events = await self._repo.claim_pending(session)
            await session.commit()
        if not events:
            return 0
        delivered = 0
        async with httpx.AsyncClient(base_url=settings.audit_ingest_url.rstrip("/"), timeout=5.0) as client:
            for event in events:
                async with self._sessions() as session:
                    try:
                        response = await client.post(
                            "/internal/v1/audit/events",
                            json=self.to_ingest(event),
                            headers={
                                "X-Internal-Service": self._service_name,
                                "X-Internal-Token": settings.audit_ingest_secret,
                            },
                        )
                        row = await session.get(self._model, event.event_id)
                        if row is None:
                            continue
                        if response.status_code < 300:
                            await self._repo.mark_delivered(session, row)
                            delivered += 1
                        else:
                            await self._repo.mark_retry(
                                session,
                                row,
                                error=f"http:{response.status_code}",
                                max_attempts=settings.worker_max_attempts,
                            )
                        await session.commit()
                    except httpx.HTTPError as exc:
                        row = await session.get(self._model, event.event_id)
                        if row is not None:
                            await self._repo.mark_retry(
                                session,
                                row,
                                error=f"network:{exc.__class__.__name__}",
                                max_attempts=settings.worker_max_attempts,
                            )
                            await session.commit()
                        self._logger.warning(
                            f"{self._log_name}_audit_deliver_failed", event_id=str(event.event_id)
                        )
        return delivered

    async def outbox_loop(self, stop: asyncio.Event, settings: _AuditSettings) -> None:
        while not stop.is_set():
            try:
                await self.deliver_pending(settings)
            except Exception:  # noqa: BLE001
                self._logger.exception(f"{self._log_name}_outbox_loop_failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_interval_seconds)
            except TimeoutError:
                continue
