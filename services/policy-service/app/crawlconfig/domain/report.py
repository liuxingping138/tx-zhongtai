"""爬虫配置统计的口径：信源表一行算一个栏目，按上线时间落在哪一期（自然周、月、季度、年）统计配置数量。

上线时间是统一补填日的（不知道真实配置日）和已爬没填上线时间的算期初存量，不算进任何一期。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

Unit = Literal["week", "month", "quarter", "year"]
UNITS: tuple[Unit, ...] = ("week", "month", "quarter", "year")
# 周往前看 12 周（含本周）；年看到最早有数据的那年为止，最多 10 年。月、季度只画今年的 12 个月、4 个季度。
WINDOW: dict[Unit, int] = {"week": 12, "year": 10}
_MONTHS: dict[Unit, int] = {"month": 1, "quarter": 3, "year": 12}
BLANK_PROVINCE = "（未填省份）"


def period_start(day: date, unit: Unit) -> date:
    if unit == "week":
        return day - timedelta(days=day.weekday())
    months = _MONTHS[unit]
    return date(day.year, (day.month - 1) // months * months + 1, 1)


def shift(start: date, unit: Unit, count: int) -> date:
    """start 所在这期往后（负数往前）挪 count 期，返回那一期的第一天。"""

    start = period_start(start, unit)
    if unit == "week":
        return start + timedelta(weeks=count)
    index = start.year * 12 + start.month - 1 + count * _MONTHS[unit]
    return date(index // 12, index % 12 + 1, 1)


def period_end(start: date, unit: Unit) -> date:
    return shift(start, unit, 1) - timedelta(days=1)


def default_period(today: date, unit: Unit) -> date:
    """周看上周：爬虫同事周五批量建规则，周一汇报的是上一整周；月、季度、年看当前这期，到今天为止。"""

    current = period_start(today, unit)
    return shift(current, unit, -1) if unit == "week" else current


def window(today: date, unit: Unit, earliest: date | None) -> list[date]:
    """柱图的各期（第一天），从早到晚。

    月、季度是今年的 1–12 月、第一到第四季度，还没到的那几期也画出来（为 0），横轴固定不随月份滑动；
    周、年的最后一期是今天所在这期，年只从最早有数据的那年画起。
    """

    if unit in ("month", "quarter"):
        first = date(today.year, 1, 1)
        return [shift(first, unit, offset) for offset in range(12 // _MONTHS[unit])]
    count = WINDOW[unit]
    if unit == "year" and earliest is not None:
        count = min(count, today.year - earliest.year + 1)
    current = period_start(today, unit)
    return [shift(current, unit, offset) for offset in range(1 - max(count, 1), 1)]


def _parse_day(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def earliest(daily: dict[str, int]) -> date | None:
    days = [day for day in map(_parse_day, daily) if day is not None]
    return min(days, default=None)


def count_between(daily: dict[str, int], start: date, end: date) -> int:
    total = 0
    for text, number in daily.items():
        day = _parse_day(text)
        if day is not None and start <= day <= end:
            total += number
    return total


def series(daily: dict[str, int], starts: list[date], unit: Unit) -> list[dict[str, Any]]:
    """每期配置了多少网站；daily 是按上线日期的计数（已去掉期初）。"""

    counts = dict.fromkeys(starts, 0)
    for text, number in daily.items():
        day = _parse_day(text)
        if day is not None and (start := period_start(day, unit)) in counts:
            counts[start] += number
    return [
        {"period_from": start.isoformat(), "period_to": period_end(start, unit).isoformat(), "new": number}
        for start, number in counts.items()
    ]


def province_order(row: dict[str, Any]) -> tuple[int, str, str]:
    """按省份编码排（和码表、信源表透视的省份顺序一致），没有编码的排后面，没填省份的排最后。"""

    name = str(row.get("province_name") or "")
    code = str(row.get("province_code") or "")
    return (2 if not name else 1 if not code else 0, code, name)


def coverage(online: int, total: int) -> float:
    """已爬占比，保留一位小数的百分数。"""

    return round(online * 100 / total, 1) if total else 0.0
