"""短期内存缓存避免重复扫描源库；不落库、不改源表。"""

from collections import OrderedDict
from datetime import timedelta
from threading import BoundedSemaphore, Event, Lock
from time import monotonic

from platform_common.clock import BEIJING, utcnow
from platform_common.errors import DependencyUnavailableError

from app.core.config import get_settings
from app.core.source import Row, source_reader
from app.domain.fields import Kind
from app.domain.queries import StatsQuery
from app.repositories import statistics


class _InFlight:
    """同一个日期区间的并发统计请求合并成一次源库扫描，避免重复查或彼此阻塞。"""

    def __init__(self) -> None:
        self.done = Event()
        self.result: Row | None = None
        self.error: BaseException | None = None


_cache: OrderedDict[str, tuple[float, Row]] = OrderedDict()
_inflight: dict[str, _InFlight] = {}
_lock = Lock()
_COMPUTE_SEM = BoundedSemaphore(4)
_MAX_CACHE_ENTRIES = 128
KINDS: tuple[Kind, ...] = ("purchaser", "winbid")


def _cached_locked(key: str) -> Row | None:
    entry = _cache.get(key)
    if entry and monotonic() - entry[0] < get_settings().stats_cache_seconds:
        return entry[1]
    return None


def _store(key: str, result: Row) -> Row:
    with _lock:
        _cache[key] = (monotonic(), result)
        _cache.move_to_end(key)
        while len(_cache) > _MAX_CACHE_ENTRIES:
            _cache.popitem(last=False)
        return result


def _point(label: str, value: str) -> Row:
    row: Row = {label: value, "purchaser": 0, "winbid": 0, "tagged": 0, "enriched": 0, "scenario": 0}
    if label == "province":
        row["purchaser_passed"] = 0
        row["winbid_passed"] = 0
    return row


def _wait_flight(flight: _InFlight) -> Row:
    if not flight.done.wait(timeout=95):
        raise DependencyUnavailableError("统计查询等待超时，请稍后重试")
    if flight.error is not None:
        raise flight.error
    if flight.result is None:
        raise DependencyUnavailableError("统计结果未就绪，请稍后重试")
    return flight.result


def get_statistics(query: StatsQuery) -> Row:
    key = f"{query.date_from}:{query.date_to}"
    flight: _InFlight | None = None
    leader = False
    with _lock:
        cached = _cached_locked(key)
        if cached is not None:
            return cached
        flight = _inflight.get(key)
        if flight is None:
            flight = _InFlight()
            _inflight[key] = flight
            leader = True

    if not leader:
        return _wait_flight(flight)

    if not _COMPUTE_SEM.acquire(blocking=False):
        err = DependencyUnavailableError("当前统计查询较多，请稍后重试")
        with _lock:
            _inflight.pop(key, None)
        flight.error = err
        flight.done.set()
        raise err

    try:
        result = _aggregate(query)
        _store(key, result)
        flight.result = result
        return result
    except BaseException as exc:
        flight.error = exc
        raise
    finally:
        with _lock:
            _inflight.pop(key, None)
        _COMPUTE_SEM.release()
        flight.done.set()


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
                    processed = int(row["processed"] or 0)
                    for target in (point, province):
                        target[kind] += int(row["total"])
                        target["tagged"] += processed
                        target["enriched"] += processed
                    if kind == "purchaser":
                        province["purchaser_passed"] += processed
                    elif kind == "winbid":
                        province["winbid_passed"] += processed
            daily.append(point)
    return {
        "daily": daily,
        "provinces": sorted(provinces.values(), key=lambda row: row["purchaser"] + row["winbid"], reverse=True),
        "date_from": query.date_from.isoformat(),
        "date_to": query.date_to.isoformat(),
        "as_of": utcnow().astimezone(BEIJING).isoformat(),
    }
