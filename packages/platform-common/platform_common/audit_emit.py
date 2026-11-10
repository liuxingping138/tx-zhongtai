"""业务事件入 Outbox、再投递到审计服务。

各业务服务的投递机制完全一致，只有事件映射表、服务名和 ORM model 不同，
所以这里参数化成 ``AuditEmitter``，服务内只保留自己的事件映射。

投递失败不丢事件：失败会回写 Outbox 并按指数退避重试，达到上限后置为 dead。
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any, Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_common.actors import Actor
from platform_common.clock import utcnow
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


# enqueue_event 自己放进 payload 的键；其余顶层键都是调用方的 extra（批量操作改了哪些记录、条数等）。
_BASE_KEYS = frozenset({"actor_id", "actor_name", "target_id", "outcome", "request_id", "changes"})
# 审计服务单条事件上限 32KB，超了直接拒收、这条进 dead：变更内容留足余量，太长的清单截短并注明原数。
_CHANGES_MAX_BYTES = 24_000
# 已投递的出站记录保留 30 天（审计服务那边早已入库，这里只留着排查投递问题），每小时清一次、一批 5000 条。
OUTBOX_RETENTION = timedelta(days=30)
PURGE_EVERY_SECONDS = 3600.0
PURGE_BATCH = 5000


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str).encode())


def _fit(changes: dict[str, Any]) -> dict[str, Any]:
    """变更内容太大时，把最长的清单一半一半地截短，记下原来有几项，宁可少列几个 ID 也不能整条审计丢掉。"""

    fitted = dict(changes)
    while _size(fitted) > _CHANGES_MAX_BYTES:
        lists = [(len(value), key) for key, value in fitted.items() if isinstance(value, list) and len(value) > 1]
        if not lists:
            break
        _, key = max(lists)
        fitted.setdefault(f"{key}_总数", len(changes[key]))
        fitted[key] = fitted[key][: len(fitted[key]) // 2]
    return fitted


def ingest_changes(payload: dict[str, Any]) -> Any:
    """审计里的「变更」：调用方给的 changes 加上 extra。原来只要有 changes 就把 extra 整个丢掉，
    批量改状态、重新打标这类操作「改了哪些记录」从没进过操作日志。没有 changes 时照旧给整个 payload。"""

    changes = payload.get("changes")
    if not changes:
        return _fit(payload)
    extra = {key: value for key, value in payload.items() if key not in _BASE_KEYS}
    return _fit({**changes, **extra}) if extra else _fit(changes)


# 审计服务拒收、重试也不会变的响应：内容格式不对、超过大小上限、字段校验不过。
PERMANENT_REJECTIONS = frozenset({400, 413, 422})


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
        event_meta: EventMeta,
        outbox_model: type[Any],
        session_factory: async_sessionmaker[AsyncSession],
        get_settings: Callable[[], _AuditSettings],
    ) -> None:
        self._service_name = service_name
        self._event_meta = event_meta
        self._model = outbox_model
        self._sessions = session_factory
        self._get_settings = get_settings
        self._repo = OutboxRepository(outbox_model)
        # 日志前缀和未登记事件的默认模块都取服务名前缀：policy-service → policy。
        self._log_name = service_name.removesuffix("-service")
        self._default_module = self._log_name
        self._logger = get_logger(f"{self._log_name}.audit")

    async def enqueue_event(
        self,
        session: AsyncSession,
        *,
        event_type: str,
        actor: Actor,
        target_id: str | None = None,
        changes: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "actor_id": actor.id,
            "actor_name": actor.name,
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
            "changes": ingest_changes(payload),
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
                if await self._deliver_one(client, settings, event):
                    delivered += 1
        return delivered

    async def _deliver_one(self, client: httpx.AsyncClient, settings: _AuditSettings, event: Any) -> bool:
        """投递一条并按租约回写结果。任何异常都落到失败重试，不让一条坏事件拖住整批。"""

        expected_lease = event.lease_until
        error: str | None = None
        attempts = event.attempts
        try:
            response = await client.post(
                "/internal/v1/audit/events",
                json=self.to_ingest(event),
                headers={
                    "X-Internal-Service": self._service_name,
                    "X-Internal-Token": settings.audit_ingest_secret,
                },
            )
            if not response.is_success:
                error = f"http:{response.status_code}"
                # 只有内容本身不合格（400/413/422）重试多少次都不会变，直接置 dead。401/403 多半是两边换密钥、
                # 容器重建有先后，几分钟后就好；当它们也直接 dead，轮换一次密钥就丢一批审计。
                if response.status_code in PERMANENT_REJECTIONS:
                    attempts = settings.worker_max_attempts
        except httpx.HTTPError as exc:
            error = f"network:{exc.__class__.__name__}"
        except Exception as exc:  # 组装投递体等本地异常，按失败重试到上限后置 dead
            self._logger.exception(f"{self._log_name}_audit_deliver_error", event_id=str(event.event_id))
            error = f"error:{exc.__class__.__name__}"

        async with self._sessions() as session:
            if error is None:
                ok = await self._repo.mark_delivered(session, event.event_id, expected_lease)
            else:
                ok = await self._repo.mark_retry(
                    session,
                    event.event_id,
                    expected_lease,
                    attempts=attempts,
                    error=error,
                    max_attempts=settings.worker_max_attempts,
                )
            await session.commit()
        if not ok:
            self._logger.warning(f"{self._log_name}_outbox_lease_lost", event_id=str(event.event_id))
        elif error is not None and attempts >= settings.worker_max_attempts:
            self._logger.error(f"{self._log_name}_audit_event_parked", event_id=str(event.event_id), error=error)
        elif error is not None:
            self._logger.warning(f"{self._log_name}_audit_deliver_failed", event_id=str(event.event_id), error=error)
        return ok and error is None

    async def purge_delivered(self, *, now: datetime | None = None) -> int:
        """已投递的出站记录保留 OUTBOX_RETENTION，分批删，每批一个事务，不长时间占着表。"""

        before = (now or utcnow()) - OUTBOX_RETENTION
        total = 0
        while True:
            async with self._sessions() as session:
                deleted = await self._repo.purge_delivered(session, before=before, limit=PURGE_BATCH)
                await session.commit()
            total += deleted
            if deleted < PURGE_BATCH:
                break
        if total:
            self._logger.info(f"{self._log_name}_outbox_purged", deleted=total)
        return total

    async def outbox_loop(self, stop: asyncio.Event, settings: _AuditSettings) -> None:
        next_purge = 0.0
        while not stop.is_set():
            try:
                await self.deliver_pending(settings)
                if time.monotonic() >= next_purge:
                    next_purge = time.monotonic() + PURGE_EVERY_SECONDS
                    await self.purge_delivered()
            except Exception:
                self._logger.exception(f"{self._log_name}_outbox_loop_failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_interval_seconds)
            except TimeoutError:
                continue
