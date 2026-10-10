from __future__ import annotations

from dataclasses import dataclass

from platform_common.filters import FilterValue


@dataclass(frozen=True, slots=True)
class UserFilters:
    """用户列表的筛选条件。列表、计数和导出共用同一份，所见即所导。"""

    username: FilterValue = None
    status: FilterValue = None
    # 角色 id 之外还接受 none，表示「待分配角色」。
    role_id: FilterValue = None
    # 同时匹配用户名、显示名、电话、邮箱。
    keyword: FilterValue = None
