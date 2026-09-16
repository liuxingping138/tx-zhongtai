"""IAM 领域枚举。"""

from __future__ import annotations

from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class RoleStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class NodeType(StrEnum):
    DIRECTORY = "directory"
    RESOURCE = "resource"


class GrantLevel(StrEnum):
    READ = "READ"
    FULL = "FULL"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"
    DEAD = "dead"


class SecurityClass(StrEnum):
    """路由安全分类。每个外部/内部路由必须显式声明，供覆盖测试发现遗漏。"""

    PUBLIC_AUTH = "public_auth"
    RESTRICTED_SESSION = "restricted_session"
    AUTHENTICATED = "authenticated"
    RESOURCE_AUTHORIZED = "resource_authorized"
    INTERNAL = "internal"
    HEALTH = "health"
