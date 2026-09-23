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
    """授权档位，逐档包含：查看 < 查看+导出 < 管理（含新增、编辑、导入等写操作）。"""

    READ = "READ"
    # 导出单列一档：能看不等于能把整表数据带走。
    EXPORT = "EXPORT"
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
