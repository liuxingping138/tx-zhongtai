"""限定公司网络的模块（智库）：鉴权时按来源 IP 核对公司网络和这个人的访问白名单。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from platform_common.clock import format_beijing, utcnow
from platform_common.errors import NetworkDeniedError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domain.catalog import RESOURCE_SPECS
from app.domain.networks import contains, office_networks, parse_address, range_contains, split_items
from app.repositories import ip_whitelist as repo

Via = Literal["office", "whitelist", "disabled", ""]

_ROOT_NAMES = {spec.code: spec.name for spec in RESOURCE_SPECS if "." not in spec.code}


@dataclass(frozen=True)
class NetworkDecision:
    ip: str
    allowed: bool
    # office：公司网络；whitelist：管理员开的白名单；disabled：本环境没开限制
    via: Via = ""
    expires_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        return {"ip": self.ip, "allowed": self.allowed, "via": self.via, "expires_at": format_beijing(self.expires_at)}


def restricted_prefixes(settings: Settings) -> list[str]:
    return split_items(settings.network_restricted_prefixes)


def is_restricted(settings: Settings, resource_code: str) -> bool:
    return settings.network_guard_enabled and any(resource_code.startswith(p) for p in restricted_prefixes(settings))


def restricted_module_names(settings: Settings) -> list[str]:
    """页面上说「哪些模块只能在公司网络用」：取前缀对应的一级目录名。"""

    roots = [prefix.split(".")[0] for prefix in restricted_prefixes(settings)]
    return [_ROOT_NAMES.get(root, root) for root in roots]


async def decide(
    session: AsyncSession, settings: Settings, user_id: uuid.UUID, ip: str | None, *, now: datetime | None = None
) -> NetworkDecision:
    shown_ip = ip or ""
    if not settings.network_guard_enabled:
        return NetworkDecision(ip=shown_ip, allowed=True, via="disabled")
    addr = parse_address(ip)
    if addr is None:
        return NetworkDecision(ip=shown_ip, allowed=False)
    if contains(office_networks(split_items(settings.office_networks)), addr):
        return NetworkDecision(ip=shown_ip, allowed=True, via="office")
    rows = await repo.active_ranges_for_user(session, user_id, now or utcnow())
    expiries = [expires_at for ip_range, expires_at in rows if range_contains(ip_range, addr)]
    if not expiries:
        return NetworkDecision(ip=shown_ip, allowed=False)
    return NetworkDecision(ip=shown_ip, allowed=True, via="whitelist", expires_at=max(expiries))


def denied_message(resource_code: str, ip: str) -> str:
    module = _ROOT_NAMES.get(resource_code.split(".", maxsplit=1)[0], "这个模块")
    where = f"你当前的 IP 是 {ip}，" if ip else "没能识别你的来源 IP，"
    return f"{module}只能在公司网络下访问。{where}如需在其他地方使用，请把这个 IP 发给管理员开通访问白名单。"


async def assert_network_allowed(
    session: AsyncSession, settings: Settings, user_id: uuid.UUID, resource_code: str, ip: str | None
) -> None:
    """资源不限定网络就直接过；限定的话公司网络或这个人的有效白名单才放行，否则 403 NETWORK_DENIED。

    业务服务没带来源 IP 时按拒绝处理（不能因为少传一个字段就绕过）。
    """

    if not is_restricted(settings, resource_code):
        return
    decision = await decide(session, settings, user_id, ip)
    if not decision.allowed:
        raise NetworkDeniedError(denied_message(resource_code, decision.ip))
