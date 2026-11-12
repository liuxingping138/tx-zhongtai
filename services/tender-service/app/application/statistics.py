"""短期内存缓存避免重复扫描源库；不落库、不改源表。"""

from collections import OrderedDict
from datetime import timedelta
from threading import Lock
from time import monotonic

from platform_common.clock import BEIJING, utcnow
from platform_common.errors import DependencyUnavailableError

from app.core.config import get_settings
from app.core.source import Row, source_reader
from app.domain.fields import Kind
from app.domain.queries import StatsQuery
from app.repositories import statistics

_cache: OrderedDict[str, tuple[float, Row]] = OrderedDict()
_lock = Lock()
_MAX_CACHE_ENTRIES = 128
KINDS: tuple[Kind, ...] = ("purchaser", "winbid")


def _cached(key: str) -> Row | None:
    entry = _cache.get(key)
    if entry and monotonic() - entry[0] < get_settings().stats_cache_seconds:
        return entry[1]
    return None


def _store(key: str, result: Row) -> Row:
    _cache[key] = (monotonic(), result)
    _cache.move_to_end(key)
    while len(_cache) > _MAX_CACHE_ENTRIES:
        _cache.popitem(last=False)
    return result


def _point(label: str, value: str) -> Row:
    return {label: value, "purchaser": 0, "winbid": 0, "tagged": 0, "enriched": 0, "scenario": 0}


def get_statistics(query: StatsQuery) -> Row:
    key = f"{query.date_from}:{query.date_to}"
    cached = _cached(key)
    if cached is not None:
        return cached
    if not _lock.acquire(blocking=False):
        raise DependencyUnavailableError("已有统计查询正在执行，请稍后重试")
    try:
        cached = _cached(key)
        if cached is not None:
            return cached
        result = _aggregate(query)
        return _store(key, result)
    finally:
        _lock.release()


def _aggregate(query: StatsQuery) -> Row:
    deadline = monotonic() + 90
    daily: list[Row] = []
    provinces: dict[str, Row] = {}
    with source_reader() as reader:
        for offset in range((query.date_to - query.date_from).days + 1):
            day = query.date_from + timedelta(days=offset)
            point = _point("date", day.isoformat())
            for kind in KINDS:
                if monotonic() > deadline:
                    raise DependencyUnavailableError("该日期范围查询较慢，请缩短日期范围后重试")
                for row in statistics.daily(reader, kind, day):
                    name = str(row["province"] or "未填写省份")
                    province = provinces.setdefault(name, _point("province", name))
                    for target in (point, province):
                        target[kind] += int(row["total"])
                        target["tagged"] += int(row["processed"] or 0)
                        target["enriched"] += int(row["processed"] or 0)
            daily.append(point)
    return {
        "daily": daily,
        "provinces": sorted(provinces.values(), key=lambda row: row["purchaser"] + row["winbid"], reverse=True),
        "date_from": query.date_from.isoformat(),
        "date_to": query.date_to.isoformat(),
        "as_of": utcnow().astimezone(BEIJING).isoformat(),
    }
