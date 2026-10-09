"""用户 Excel 的列清单。表头与页面列名一致。"""

from __future__ import annotations

from platform_common.columns import ColumnSpec

USER_IMPORT_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("username", "用户名"),
    ColumnSpec("display_name", "显示名"),
    ColumnSpec("phone", "电话"),
    ColumnSpec("email", "邮箱"),
    # 角色名称，多个用顿号或逗号分隔。只有能分配角色的人导入时才生效。
    ColumnSpec("roles", "角色"),
)

USER_EXPORT_COLUMNS: tuple[ColumnSpec, ...] = (
    *USER_IMPORT_COLUMNS,
    ColumnSpec("status", "状态"),
    ColumnSpec("created_at", "创建时间"),
)

STATUS_TEXT = {"active": "启用", "disabled": "禁用"}
