"""权限判定纯函数。不访问数据库，便于单测。"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from enum import StrEnum

from app.domain.enums import GrantLevel, UserStatus

LEVEL_RANK = {
    None: 0,
    "NONE": 0,
    GrantLevel.READ: 1,
    "READ": 1,
    GrantLevel.EXPORT: 2,
    "EXPORT": 2,
    GrantLevel.FULL: 3,
    "FULL": 3,
}
SYSTEM_PERMISSIONS_CODE = "system.permissions"


class AuthzDecision(StrEnum):
    ALLOW = "allow"
    DENY_UNPUBLISHED = "deny_unpublished"
    DENY_UNKNOWN = "deny_unknown"
    DENY_LEVEL = "deny_level"
    DENY_ACCOUNT = "deny_account"


def max_level(levels: Iterable[str | None]) -> str | None:
    """多个启用角色取最高档；NONE/缺席不抵消其他角色。"""

    best_rank = 0
    result: str | None = None
    for level in levels:
        rank = LEVEL_RANK.get(level, 0)
        if rank > best_rank:
            best_rank = rank
            result = str(level)
    return result


def level_satisfies(effective: str | None, required: str) -> bool:
    return LEVEL_RANK.get(effective, 0) >= LEVEL_RANK.get(required, 99)


def evaluate_authorization(
    *,
    account_active: bool,
    resource_published: bool | None,
    action_required_level: str | None,
    effective_level: str | None,
) -> AuthzDecision:
    """未知资源/未知动作/未发布一律拒绝，包括超级管理员。"""

    if not account_active:
        return AuthzDecision.DENY_ACCOUNT
    if resource_published is None:
        return AuthzDecision.DENY_UNKNOWN
    if not resource_published:
        return AuthzDecision.DENY_UNPUBLISHED
    if action_required_level is None:
        return AuthzDecision.DENY_UNKNOWN
    if not level_satisfies(effective_level, action_required_level):
        return AuthzDecision.DENY_LEVEL
    return AuthzDecision.ALLOW


def remaining_loginable_superadmins(
    records: Sequence[tuple[uuid.UUID, str]],
    *,
    target_id: uuid.UUID,
    target_new_status: str | None = None,
    remove_role: bool = False,
) -> int:
    """计算变更后仍可登录的超级管理员数量。并发保护由调用方加锁。"""

    count = 0
    for user_id, status in records:
        if user_id == target_id and remove_role:
            continue
        effective_status = target_new_status if user_id == target_id and target_new_status is not None else status
        if effective_status == UserStatus.ACTIVE:
            count += 1
    return count
