"""访问白名单维护：给某个人按 IP 开通、修改（续期）、删除，写操作都上报审计。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from platform_common.clock import assume_beijing, format_beijing, utcnow
from platform_common.errors import ApiError, ErrorCode, NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import network_access
from app.core.config import Settings
from app.domain.enums import UserStatus
from app.domain.models import IpWhitelistEntry, User
from app.domain.networks import InvalidNetworkError, normalize_network, split_items
from app.repositories import ip_whitelist as repo
from app.repositories import outbox as outbox_repo
from app.repositories import users as user_repo

# 时效最短 10 分钟：再短开通了对方还没来得及打开就过期了。
MIN_DURATION = timedelta(minutes=10)


@dataclass(frozen=True)
class WhitelistInput:
    user_id: uuid.UUID
    ip_range: str
    reason: str
    expires_at: datetime


def _invalid(message: str) -> ApiError:
    return ApiError(message, code=ErrorCode.VALIDATION_ERROR, http_status=422)


def _user_out(user: User) -> dict[str, str]:
    return {"id": str(user.id), "username": user.username, "display_name": user.display_name}


def to_out(entry: IpWhitelistEntry, user: User, now: datetime) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "user": _user_out(user),
        "ip_range": entry.ip_range,
        "reason": entry.reason,
        "expires_at": format_beijing(entry.expires_at),
        "active": entry.expires_at > now,
        "created_by_name": entry.created_by_name,
        "created_at": format_beijing(entry.created_at),
        "updated_by_name": entry.updated_by_name,
        "updated_at": format_beijing(entry.updated_at),
    }


async def overview(session: AsyncSession, settings: Settings, *, actor: User, ip: str) -> dict[str, Any]:
    """页面一次拿全：白名单、公司网络、限定网络的模块、管理员自己此刻的 IP 和判定结果。"""

    now = utcnow()
    rows = await repo.list_entries(session)
    decision = await network_access.decide(session, settings, actor.id, ip, now=now)
    return {
        "items": [to_out(entry, user, now) for entry, user in rows],
        "office_networks": split_items(settings.office_networks),
        "restricted_modules": network_access.restricted_module_names(settings),
        "guard_enabled": settings.network_guard_enabled,
        "max_days": settings.whitelist_max_days,
        "current": {**decision.to_dict(), "user": _user_out(actor)},
    }


async def user_options(session: AsyncSession, keyword: str) -> list[dict[str, str]]:
    return [_user_out(user) for user in await repo.search_users(session, keyword)]


async def _require_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await user_repo.get_user_by_id(session, user_id)
    if user is None or user.status == UserStatus.DELETED:
        raise _invalid("这个用户不存在或已删除，请重新选择")
    return user


def _clean(settings: Settings, data: WhitelistInput, now: datetime) -> WhitelistInput:
    try:
        ip_range = normalize_network(data.ip_range)
    except InvalidNetworkError as exc:
        raise _invalid(str(exc)) from exc
    expires_at = assume_beijing(data.expires_at)
    if expires_at is None:
        raise _invalid("请选择到期时间")
    if expires_at < now + MIN_DURATION:
        raise _invalid("到期时间至少要在 10 分钟以后")
    if expires_at > now + timedelta(days=settings.whitelist_max_days, minutes=5):
        raise _invalid(f"一次最多开通 {settings.whitelist_max_days} 天，到期后再续")
    return WhitelistInput(user_id=data.user_id, ip_range=ip_range, reason=data.reason.strip(), expires_at=expires_at)


async def _reject_duplicate(
    session: AsyncSession, data: WhitelistInput, user: User, now: datetime, *, exclude_id: uuid.UUID | None = None
) -> None:
    existing = await repo.find_active_duplicate(session, data.user_id, data.ip_range, now, exclude_id=exclude_id)
    if existing is not None:
        until = format_beijing(existing.expires_at)
        raise ApiError(
            f"{user.display_name} 的 {data.ip_range} 已有一条没到期的白名单（到期 {until}），在那条上修改到期时间即可",
            code=ErrorCode.DUPLICATE,
            http_status=409,
        )


def _audit_fields(entry: IpWhitelistEntry | WhitelistInput, user: User) -> dict[str, str]:
    return {
        "user_id": str(user.id),
        "username": user.username,
        "ip_range": entry.ip_range,
        "reason": entry.reason,
        "expires_at": format_beijing(entry.expires_at),
    }


async def create_entry(
    session: AsyncSession, settings: Settings, *, actor: User, data: WhitelistInput
) -> dict[str, Any]:
    now = utcnow()
    user = await _require_user(session, data.user_id)
    clean = _clean(settings, data, now)
    await _reject_duplicate(session, clean, user, now)
    entry = IpWhitelistEntry(
        id=uuid.uuid4(),
        user_id=user.id,
        ip_range=clean.ip_range,
        reason=clean.reason,
        expires_at=clean.expires_at,
        created_by=actor.id,
        created_by_name=actor.display_name,
        created_at=now,
        updated_by=actor.id,
        updated_by_name=actor.display_name,
        updated_at=now,
    )
    repo.add(session, entry)
    await session.flush()
    await outbox_repo.enqueue(
        session,
        event_type="iam.ip_whitelist.created",
        payload={
            "actor_id": str(actor.id),
            "target_id": str(entry.id),
            **_audit_fields(clean, user),
            "outcome": "success",
        },
    )
    return to_out(entry, user, now)


async def _require_entry(session: AsyncSession, entry_id: uuid.UUID) -> IpWhitelistEntry:
    entry = await repo.get_entry(session, entry_id)
    if entry is None:
        raise NotFoundError("这条白名单不存在或已被删除")
    return entry


async def update_entry(
    session: AsyncSession, settings: Settings, *, actor: User, entry_id: uuid.UUID, data: WhitelistInput
) -> dict[str, Any]:
    now = utcnow()
    entry = await _require_entry(session, entry_id)
    before_user = await _require_user(session, entry.user_id)
    user = await _require_user(session, data.user_id)
    clean = _clean(settings, data, now)
    await _reject_duplicate(session, clean, user, now, exclude_id=entry.id)
    before = _audit_fields(entry, before_user)
    entry.user_id = user.id
    entry.ip_range = clean.ip_range
    entry.reason = clean.reason
    entry.expires_at = clean.expires_at
    entry.updated_by = actor.id
    entry.updated_by_name = actor.display_name
    entry.updated_at = now
    after = _audit_fields(clean, user)
    changes = {key: {"before": before[key], "after": after[key]} for key in after if before[key] != after[key]}
    await outbox_repo.enqueue(
        session,
        event_type="iam.ip_whitelist.updated",
        payload={
            "actor_id": str(actor.id),
            "target_id": str(entry.id),
            "username": user.username,
            "ip_range": entry.ip_range,
            "changes": changes,
            "outcome": "success",
        },
    )
    return to_out(entry, user, now)


async def delete_entry(session: AsyncSession, *, actor: User, entry_id: uuid.UUID) -> None:
    entry = await _require_entry(session, entry_id)
    user = await user_repo.get_user_by_id(session, entry.user_id)
    fields = _audit_fields(entry, user) if user is not None else {"ip_range": entry.ip_range}
    await repo.remove(session, entry)
    await outbox_repo.enqueue(
        session,
        event_type="iam.ip_whitelist.deleted",
        payload={"actor_id": str(actor.id), "target_id": str(entry_id), **fields, "outcome": "success"},
    )
