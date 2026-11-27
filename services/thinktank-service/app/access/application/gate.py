"""判定一个来源 IP 能不能用智库：公司网络直接放行，其余看有没有没到期的白名单。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from platform_common.clock import format_beijing, utcnow
from platform_common.errors import ApiError
from sqlalchemy.ext.asyncio import AsyncSession

from app.access.domain.networks import contains, office_networks, parse_address, range_contains
from app.access.repositories import whitelist as repo
from app.core.config import Settings

NETWORK_DENIED_CODE = "THINKTANK_NETWORK_DENIED"

Via = Literal["office", "whitelist", "disabled", ""]


@dataclass(frozen=True)
class NetworkDecision:
    ip: str
    allowed: bool
    # office：公司网络；whitelist：管理员开的白名单；disabled：本环境没开限制
    via: Via = ""
    expires_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "ip": self.ip,
            "allowed": self.allowed,
            "via": self.via,
            "expires_at": format_beijing(self.expires_at),
        }


class NetworkDeniedError(ApiError):
    """不在公司网络、也没有有效白名单。前端认 code 跳到说明页，提示里带上 IP 方便发给管理员。"""

    http_status = 403
    code = NETWORK_DENIED_CODE

    def __init__(self, ip: str) -> None:
        super().__init__(
            f"智库只能在公司网络下访问。你当前的 IP 是 {ip}，如需在其他地方使用，请把这个 IP 发给管理员开通临时白名单。"
        )


async def decide(session: AsyncSession, settings: Settings, ip: str, *, now: datetime | None = None) -> NetworkDecision:
    if not settings.network_guard_enabled:
        return NetworkDecision(ip=ip, allowed=True, via="disabled")
    addr = parse_address(ip)
    if addr is None:
        return NetworkDecision(ip=ip, allowed=False)
    if contains(office_networks(settings.office_network_items()), addr):
        return NetworkDecision(ip=ip, allowed=True, via="office")
    rows = await repo.active_ranges(session, now or utcnow())
    expiries = [expires_at for ip_range, expires_at in rows if range_contains(ip_range, addr)]
    if not expiries:
        return NetworkDecision(ip=ip, allowed=False)
    return NetworkDecision(ip=ip, allowed=True, via="whitelist", expires_at=max(expiries))
