"""爬虫配置统计的口径：信源表一行算一个栏目，按上线时间落在哪个自然周（周一到周日）统计每周新增。

统计起始周之前上线的（含首次同步一次性标上的历史网站、没填上线时间的已爬）算期初存量，不算进任何一周的新增。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

TREND_WEEKS = 12
BLANK_PROVINCE = "（未填省份）"


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_end(day: date) -> date:
    return week_start(day) + timedelta(days=6)


def trend_weeks(selected: date, report_start: date, count: int = TREND_WEEKS) -> list[date]:
    """所选周往前最多 count 周（周一），不早于统计起始周；所选周还在起始周之前时为空。"""

    last, first = week_start(selected), week_start(report_start)
    first = max(first, last - timedelta(weeks=count - 1))
    weeks: list[date] = []
    while first <= last:
        weeks.append(first)
        first += timedelta(weeks=1)
    return weeks


def _parse_day(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def weekly_series(daily: dict[str, int], weeks: list[date], baseline: int) -> list[dict[str, Any]]:
    """按天的上线数加总成每周新增，以及截至每周周日的累计上线（期初存量 + 起始周以来的新增）。

    daily 是统计起始周以来按上线日期的计数；早于第一周的（所选周离起始周超过 count 周时）计入累计的起点。
    """

    if not weeks:
        return []
    counts = dict.fromkeys(weeks, 0)
    carried = baseline
    for text, number in daily.items():
        day = _parse_day(text)
        if day is None:
            continue
        monday = week_start(day)
        if monday in counts:
            counts[monday] += number
        elif monday < weeks[0]:
            carried += number
    series = []
    for monday in weeks:
        carried += counts[monday]
        series.append(
            {
                "week_from": monday.isoformat(),
                "week_to": week_end(monday).isoformat(),
                "new": counts[monday],
                "cumulative": carried,
            }
        )
    return series


def province_weekly(rows: list[tuple[str, str, int]], weeks: list[date]) -> dict[str, list[int]]:
    """各省每周新配置的栏目数，和 weeks 一一对应；不在这些周里的不算。省份为空的记在 BLANK_PROVINCE 名下。"""

    index = {monday: position for position, monday in enumerate(weeks)}
    result: dict[str, list[int]] = {}
    for province, text, number in rows:
        day = _parse_day(text)
        position = index.get(week_start(day)) if day else None
        if position is None:
            continue
        result.setdefault(province or BLANK_PROVINCE, [0] * len(weeks))[position] += number
    return result


def province_order(row: dict[str, Any]) -> tuple[int, str, str]:
    """按省份编码排（和码表、领导习惯的省份顺序一致），没有编码的排后面，没填省份的排最后。"""

    name = str(row.get("province_name") or "")
    code = str(row.get("province_code") or "")
    return (2 if not name else 1 if not code else 0, code, name)


def coverage(online: int, total: int) -> float:
    """已爬占比，保留一位小数的百分数。"""

    return round(online * 100 / total, 1) if total else 0.0
