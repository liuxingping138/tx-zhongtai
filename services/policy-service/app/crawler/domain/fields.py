"""政策三张表与 Excel 表头的对应关系。"""

from __future__ import annotations

from platform_common.columns import ColumnSpec

CRAWLER_SITE_STATUS_LABELS: dict[str, str] = {
    "normal": "正常",
    "watch": "关注",
    "stale": "停更",
}

CRAWLER_SITE_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("site_name", "网站名称", searchable=True),
    ColumnSpec("province_name", "省份", searchable=True),
    ColumnSpec("city_name", "地市", searchable=True),
    ColumnSpec("total_rows", "数据总量"),
    ColumnSpec("last_created_at", "最新入库时间"),
    ColumnSpec("last_published_date", "最近发布时间"),
    ColumnSpec("stale_days", "停更天数"),
    ColumnSpec("status_label", "状态"),
)
