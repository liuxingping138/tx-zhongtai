"""模板可引用的系统码表。键与码表服务 /internal/v1/code-tables/{name} 一致，内容每次实时取。"""

from __future__ import annotations

from platform_common.errors import ApiError, ErrorCode

SYSTEM_CODE_TABLES: dict[str, str] = {
    "policy_types": "政策类型码表",
    "scenarios": "行业场景码表（六级）",
    "scenario_l1": "行业场景码表（一级行业 + 一级场景）",
}


def code_table_name(key: str) -> str:
    return SYSTEM_CODE_TABLES.get(key, key)


def checked_code_table(value: object) -> str:
    """空串表示不用系统码表（用上传的码表文件，或者不用码表）。"""

    key = str(value or "").strip()
    if key and key not in SYSTEM_CODE_TABLES:
        raise ApiError(f"不认识的系统码表：{key}", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    return key
