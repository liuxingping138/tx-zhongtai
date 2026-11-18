"""业务线（操作日志的「类型」）：政策、客户、招投标。入库时由审计服务按模块编码和事件内容算好，存进 business_line。

政策、客户、招投标模块的事件按模块编码；AI提问按事件里记的模板类型（ai-service 入队时放进 changes.category）。
系统管理、码表管理不属于哪条业务线，为空。
"""

from __future__ import annotations

from typing import Any

BUSINESS_LINES = ("policy", "customer", "tender", "thinktank")


def business_line(module_code: str | None, changes: dict[str, Any] | None) -> str | None:
    root = (module_code or "").split(".", 1)[0]
    if root == "ai":
        category = (changes or {}).get("category")
        return category if category in BUSINESS_LINES else None
    return root if root in BUSINESS_LINES else None
