"""智库统计领域规格：库范围、时间粒度/窗口计算、分类维度与口径解析。"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Literal

LibraryKey = Literal["knowledge", "reports", "proposals"]
LibraryScope = Literal["all", "knowledge", "reports", "proposals"]
Granularity = Literal["day", "week", "month", "quarter", "year"]
RangePreset = Literal["7d", "30d", "quarter", "year", "all"]

ALL_LIBRARIES: tuple[LibraryKey, ...] = ("knowledge", "reports", "proposals")
LIBRARY_LABELS: dict[LibraryKey, str] = {
    "knowledge": "资料库",
    "reports": "报告库",
    "proposals": "方案库",
}
BJ_TZ = timezone(timedelta(hours=8))
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass(frozen=True)
class DimensionSpec:
    """单个分类统计维度的展示与下钻元数据。"""

    key: str
    label: str
    note: str = ""
    pipe_split: bool = False
    empty_label: str = "未定义"
    exclude_values: frozenset[str] = frozenset()
    show_win_banner: bool = False
    drill_field: str = ""


DIMENSIONS_BY_SCOPE: dict[LibraryScope, tuple[DimensionSpec, ...]] = {
    "all": (
        DimensionSpec("file_type", "核心类型分布", drill_field="file_type"),
        DimensionSpec(
            "industry",
            "行业赛道",
            note="不含标记为「无」的通用资料；多行业标签按对应赛道分别计入",
            pipe_split=True,
            exclude_values=frozenset({"无"}),
            drill_field="industry_type",
        ),
        DimensionSpec("dept", "部门沉淀", empty_label="未填写", drill_field="depart_affiliation"),
        DimensionSpec("region", "区域/省份", empty_label="未填写", drill_field="prov_name"),
    ),
    "knowledge": (
        DimensionSpec("file_type", "文件类型", drill_field="file_type"),
        DimensionSpec(
            "industry",
            "行业类型",
            note="不含标记为「无」的通用资料；多标签按各行业拆算",
            pipe_split=True,
            exclude_values=frozenset({"无"}),
            drill_field="industry_type",
        ),
        DimensionSpec("operator", "运营商类型", empty_label="未填写", drill_field="operator_type"),
        DimensionSpec("market", "市场类别", empty_label="未填写", drill_field="market_category"),
        DimensionSpec("province", "省份分布", empty_label="未填写", drill_field="prov_name"),
        DimensionSpec("dept", "部门归属", empty_label="未填写", drill_field="depart_affiliation"),
    ),
    "reports": (
        DimensionSpec("report_type", "报告类型", drill_field="report_type"),
        DimensionSpec(
            "industry",
            "行业赛道",
            note="多行业赛道标签按对应赛道分别计入",
            pipe_split=True,
            drill_field="industry_tags",
        ),
        DimensionSpec("delivery_dept", "交付部门", empty_label="未填写", drill_field="delivery_dept"),
        DimensionSpec("region", "区域标签", empty_label="未填写", drill_field="region_tag"),
        DimensionSpec("temp_support", "是否临时支撑", empty_label="未填写", drill_field="is_temp_support"),
    ),
    "proposals": (
        DimensionSpec("proposal_type", "方案类型", drill_field="proposal_type"),
        DimensionSpec(
            "win_result",
            "中标结果转化",
            empty_label="待补充",
            show_win_banner=True,
            drill_field="result_status",
        ),
        DimensionSpec(
            "industry",
            "行业赛道",
            note="多行业赛道标签按对应赛道分别计入",
            pipe_split=True,
            drill_field="industry_tags",
        ),
        DimensionSpec("owner_dept", "负责部门", empty_label="未填写", drill_field="owner_dept"),
        DimensionSpec("opportunity_source", "商机来源", empty_label="未填写", drill_field="opportunity_source"),
    ),
}


@dataclass(frozen=True)
class StatisticsQuery:
    """统计查询公共参数包。"""

    library: LibraryScope = "all"
    granularity: Granularity = "week"
    preset: RangePreset = "30d"
    date_from: date | None = None
    date_to: date | None = None


@dataclass(frozen=True)
class TimeWindow:
    """解析后的当前统计窗口与环比上一周期窗口（UTC 边界 + 北京日期字符串）。"""

    preset: str
    start_utc: datetime | None
    end_utc: datetime
    prev_start_utc: datetime | None
    prev_end_utc: datetime | None
    date_from: str | None
    date_to: str
    days: int


def libraries_for_scope(scope: LibraryScope) -> tuple[LibraryKey, ...]:
    return ALL_LIBRARIES if scope == "all" else (scope,)


def _day_start_utc(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=BJ_TZ).astimezone(UTC)


def _day_end_exclusive_utc(d: date) -> datetime:
    return datetime.combine(d + timedelta(days=1), time.min, tzinfo=BJ_TZ).astimezone(UTC)


def resolve_time_window(
    *,
    preset: RangePreset,
    date_from: date | None,
    date_to: date | None,
    now_utc: datetime,
) -> TimeWindow:
    """把快捷区间或自定义日期折算成左闭右开的 UTC 时间窗口和同长度环比窗口。"""

    today = now_utc.astimezone(BJ_TZ).date()
    if date_from is not None and date_to is not None:
        start_day, end_day = (date_from, date_to) if date_from <= date_to else (date_to, date_from)
        span_days = max(1, (end_day - start_day).days + 1)
        start_utc = _day_start_utc(start_day)
        end_utc = _day_end_exclusive_utc(end_day)
        prev_start = _day_start_utc(start_day - timedelta(days=span_days))
        return TimeWindow(
            preset="custom",
            start_utc=start_utc,
            end_utc=end_utc,
            prev_start_utc=prev_start,
            prev_end_utc=start_utc,
            date_from=start_day.isoformat(),
            date_to=end_day.isoformat(),
            days=span_days,
        )

    end_utc = _day_end_exclusive_utc(today)
    if preset == "all":
        return TimeWindow(
            preset="all",
            start_utc=None,
            end_utc=end_utc,
            prev_start_utc=None,
            prev_end_utc=None,
            date_from=None,
            date_to=today.isoformat(),
            days=0,
        )

    if preset == "7d":
        start_day = today - timedelta(days=6)
    elif preset == "30d":
        start_day = today - timedelta(days=29)
    elif preset == "quarter":
        q_month = ((today.month - 1) // 3) * 3 + 1
        start_day = date(today.year, q_month, 1)
    else:
        start_day = date(today.year, 1, 1)

    span_days = max(1, (today - start_day).days + 1)
    start_utc = _day_start_utc(start_day)
    prev_start = _day_start_utc(start_day - timedelta(days=span_days))
    return TimeWindow(
        preset=preset,
        start_utc=start_utc,
        end_utc=end_utc,
        prev_start_utc=prev_start,
        prev_end_utc=start_utc,
        date_from=start_day.isoformat(),
        date_to=today.isoformat(),
        days=span_days,
    )


def aggregate_classification_counts(
    raw_rows: list[tuple[str, int]],
    *,
    spec: DimensionSpec,
    limit: int = 12,
) -> list[tuple[str, int]]:
    """对原始分组值做空白归一、可选竖线拆词与降序截断。"""

    counts: Counter[str] = Counter()
    for raw_val, cnt in raw_rows:
        text = (raw_val or "").strip()
        if not text:
            counts[spec.empty_label] += cnt
            continue
        parts = [p.strip() for p in text.split("|") if p.strip()] if spec.pipe_split else [text]
        if not parts:
            counts[spec.empty_label] += cnt
            continue
        for part in parts:
            if part in spec.exclude_values:
                continue
            counts[part] += cnt
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ordered) <= limit:
        return ordered
    head = ordered[: limit - 1]
    tail_sum = sum(v for _, v in ordered[limit - 1 :])
    return [*head, ("其他合并", tail_sum)]


def parse_wan_amount(raw: str | None) -> float:
    """从报价/中标金额文本中容错提取万元数值（如 '1,280.5万' -> 1280.5）。"""

    if not raw:
        return 0.0
    cleaned = raw.replace(",", "").replace("，", "").strip()
    match = _NUM_RE.search(cleaned)
    if not match:
        return 0.0
    try:
        return max(0.0, float(match.group(0)))
    except ValueError:
        return 0.0


def compute_delta_pct(current: int, previous: int | None) -> float | None:
    """计算环比变化百分比（保留 1 位小数）；无对比基数时返回 None。"""

    if previous is None:
        return None
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) * 100.0) / previous, 1)


_SIZE_STEP = 1024.0


def format_human_size(size_bytes: int) -> str:
    """将字节数自动换算为 B / KB / MB / GB / TB，避免大库体积出现千万级 kb。"""

    if size_bytes <= 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB", "TB")
    val = float(size_bytes)
    for unit in units:
        if val < _SIZE_STEP or unit == units[-1]:
            return f"{int(val)} B" if unit == "B" else f"{val:.2f} {unit}"
        val /= _SIZE_STEP
    return f"{val:.2f} TB"


def format_bucket_label(bucket_dt: datetime, granularity: Granularity) -> str:
    """把北京时间桶起点格式化为图表横轴刻度文案。"""

    if granularity == "day":
        return bucket_dt.strftime("%m-%d")
    if granularity == "week":
        iso = bucket_dt.isocalendar()
        return f"{str(iso.year)[-2:]} W{iso.week:02d}"
    if granularity == "month":
        return bucket_dt.strftime("%Y-%m")
    if granularity == "quarter":
        q = (bucket_dt.month - 1) // 3 + 1
        return f"{bucket_dt.year} Q{q}"
    return f"{bucket_dt.year}年"
