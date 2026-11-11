from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from platform_common.filters import FilterValue


@dataclass(frozen=True, slots=True)
class EventFilters:
    """操作日志的筛选条件。计数和分页查询共用同一份，保证总数与列表口径一致。"""

    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    actor_id: str | None = None
    actor_name: FilterValue = None
    # 业务模块：模块编码的第一段（auth、system、policy……），等于这一段或以「这一段.」打头都算。
    module_root: FilterValue = None
    module_code: FilterValue = None
    business_line: FilterValue = None
    action_code: FilterValue = None
    outcome: FilterValue = None
