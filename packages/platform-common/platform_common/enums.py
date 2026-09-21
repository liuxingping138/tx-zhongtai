"""跨服务共用的枚举：路由安全分级与出站事件状态。"""

from __future__ import annotations

from enum import StrEnum


class SecurityClass(StrEnum):
    RESOURCE_AUTHORIZED = "resource_authorized"
    HEALTH = "health"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"
    DEAD = "dead"
