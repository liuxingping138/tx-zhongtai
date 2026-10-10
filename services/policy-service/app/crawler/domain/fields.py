"""政策三张表与 Excel 表头的对应关系。"""

from __future__ import annotations

from platform_common.columns import ColumnSpec

HEALTH_STATUS_LABELS: dict[str, str] = {
    "normal": "正常",
    "watch": "观察",
    "broken": "断爬",
    "never": "从未出数",
}

CRAWLER_TASK_COLUMNS: tuple[ColumnSpec, ...] = (
    ColumnSpec("province_name", "省份", searchable=True),
    ColumnSpec("city_name", "地市", searchable=True),
    ColumnSpec("site_name", "网站名称", searchable=True),
    ColumnSpec("site_code", "网站编码", searchable=True),
    ColumnSpec("tag", "标签", searchable=True),
    ColumnSpec("health_status_label", "健康状态"),
    ColumnSpec("last_collect_date", "最后采集日期"),
    ColumnSpec("stale_days", "停更天数"),
    ColumnSpec("count_7d", "近7天采集条数"),
    ColumnSpec("count_30d", "近30天采集条数"),
    ColumnSpec("count_90d", "近90天采集条数"),
    ColumnSpec("count_total", "统计窗口内累计条数"),
    ColumnSpec("in_rules_label", "爬虫规则是否仍配置"),
    ColumnSpec("source_url", "栏目源链接"),
)

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
