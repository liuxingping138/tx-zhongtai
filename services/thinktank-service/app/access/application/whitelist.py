"""白名单维护：列表、开通、修改（续期）、删除，写操作都上报审计。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from platform_common.actors import Actor
from platform_common.clock import assume_beijing, format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.application import gate
from app.access.domain.models import IpWhitelistEntry
from app.access.domain.networks import InvalidNetworkError, normalize_network
from app.access.repositories import whitelist as repo
from app.common.audit_emit import enqueue_event
from app.core.config import Settings


@dataclass(frozen=True)
class WhitelistInput:
    ip_range: str
    holder: str
    reason: str
    expires_at: datetime


def _invalid(message: str) -> ApiError:
    return ApiError(message, code=ErrorCode.VALIDATION_ERROR, http_status=422)


def to_out(entry: IpWhitelistEntry, now: datetime) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "ip_range": entry.ip_range,
        "holder": entry.holder,
        "reason": entry.reason,
        "expires_at": format_beijing(entry.expires_at),
        "active": entry.expires_at > now,
        "created_by_name": entry.created_by_name,
        "created_at": format_beijing(entry.created_at),
        "updated_by_name": entry.updated_by_name,
        "updated_at": format_beijing(entry.updated_at),
    }


async def overview(session: AsyncSession, settings: Settings, *, ip: str) -> dict[str, Any]:
    """页面一次拿全：白名单、公司网络、管理员自己此刻的 IP 和判定结果。"""

    now = utcnow()
    entries = await repo.list_entries(session)
    decision = await gate.decide(session, settings, ip, now=now)
    return {
        "items": [to_out(entry, now) for entry in entries],
        "office_networks": settings.office_network_items(),
        "guard_enabled": settings.network_guard_enabled,
        "max_days": settings.whitelist_max_days,
        "current": decision.to_dict(),
    }


def _clean(settings: Settings, data: WhitelistInput, now: datetime) -> WhitelistInput:
    try:
        ip_range = normalize_network(data.ip_range)
    except InvalidNetworkError as exc:
        raise _invalid(str(exc)) from exc
    holder = data.holder.strip()
    if not holder:
        raise _invalid("请填写使用人")
    expires_at = assume_beijing(data.expires_at)
    if expires_at is None:
        raise _invalid("请选择到期时间")
    if expires_at <= now:
        raise _invalid("到期时间要晚于现在")
    if expires_at > now + timedelta(days=settings.whitelist_max_days, minutes=5):
        raise _invalid(f"一次最多开通 {settings.whitelist_max_days} 天，到期后再续")
    return WhitelistInput(ip_range=ip_range, holder=holder, reason=data.reason.strip(), expires_at=expires_at)


async def _reject_duplicate(
    session: AsyncSession, ip_range: str, now: datetime, *, exclude_id: uuid.UUID | None = None
) -> None:
    existing = await repo.find_active_same_range(session, ip_range, now, exclude_id=exclude_id)
    if existing is not None:
        until = format_beijing(existing.expires_at)
        raise ApiError(
            f"{ip_range} 已有一条没到期的白名单（使用人 {existing.holder}，到期 {until}），在那条上修改到期时间即可",
            code=ErrorCode.DUPLICATE,
            http_status=409,
        )


def _audit_fields(data: WhitelistInput | IpWhitelistEntry) -> dict[str, str]:
    return {
        "ip_range": data.ip_range,
        "holder": data.holder,
        "reason": data.reason,
        "expires_at": format_beijing(data.expires_at),
    }


async def create_entry(
    session: AsyncSession, settings: Settings, *, actor: Actor, data: WhitelistInput
) -> dict[str, Any]:
    now = utcnow()
    clean = _clean(settings, data, now)
    await _reject_duplicate(session, clean.ip_range, now)
    entry = IpWhitelistEntry(
        id=uuid.uuid4(),
        ip_range=clean.ip_range,
        holder=clean.holder,
        reason=clean.reason,
        expires_at=clean.expires_at,
        created_by_id=actor.id,
        created_by_name=actor.name,
        created_at=now,
        updated_by_id=actor.id,
        updated_by_name=actor.name,
        updated_at=now,
    )
    repo.add(session, entry)
    await session.flush()
    await enqueue_event(
        session,
        event_type="thinktank.ip_whitelist.created",
        actor=actor,
        target_id=str(entry.id),
        changes=_audit_fields(clean),
    )
    return to_out(entry, now)


async def _require(session: AsyncSession, entry_id: uuid.UUID) -> IpWhitelistEntry:
    entry = await repo.get_entry(session, entry_id, for_update=True)
    if entry is None:
        raise NotFoundError("这条白名单不存在或已被删除")
    return entry


async def update_entry(
    session: AsyncSession, settings: Settings, *, actor: Actor, entry_id: uuid.UUID, data: WhitelistInput
) -> dict[str, Any]:
    now = utcnow()
    entry = await _require(session, entry_id)
    clean = _clean(settings, data, now)
    await _reject_duplicate(session, clean.ip_range, now, exclude_id=entry.id)
    before = _audit_fields(entry)
    entry.ip_range = clean.ip_range
    entry.holder = clean.holder
    entry.reason = clean.reason
    entry.expires_at = clean.expires_at
    entry.updated_by_id = actor.id
    entry.updated_by_name = actor.name
    entry.updated_at = now
    after = _audit_fields(clean)
    changes = {key: {"before": before[key], "after": after[key]} for key in after if before[key] != after[key]}
    await enqueue_event(
        session,
        event_type="thinktank.ip_whitelist.updated",
        actor=actor,
        target_id=str(entry.id),
        changes={"ip_range": entry.ip_range, **changes},
    )
    return to_out(entry, now)


async def delete_entry(session: AsyncSession, *, actor: Actor, entry_id: uuid.UUID) -> None:
    entry = await _require(session, entry_id)
    fields = _audit_fields(entry)
    await repo.delete(session, entry)
    await enqueue_event(
        session,
        event_type="thinktank.ip_whitelist.deleted",
        actor=actor,
        target_id=str(entry_id),
        changes=fields,
    )
