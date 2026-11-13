"""精确计数在有界线程池中执行；HTTP 轮询结果，不阻塞列表和正文。"""

from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from time import monotonic

from platform_common.clock import BEIJING, utcnow
from platform_common.errors import DependencyUnavailableError
from platform_common.logging_setup import get_logger

from app.core.config import get_settings
from app.core.source import Row, source_reader
from app.domain.fields import Kind
from app.domain.queries import ListQuery
from app.repositories import records, statistics

logger = get_logger(__name__)
_last_totals: Row | None = None
_baseline_counts: dict[tuple[Kind, str], int] = {}
_totals_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tender-totals")
_baseline_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tender-baseline")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tender-count")
_lock = Lock()
_jobs: OrderedDict[str, tuple[float, Future[Row]]] = OrderedDict()
_MAX_PENDING = 8
_MAX_ENTRIES = 128


def is_unfiltered(query: ListQuery) -> bool:
    return not (
        query.project_name.strip()
        or query.project_content_id.strip()
        or query.purchaser_provname
        or query.purchaser_cityname
        or query.purchaser_countyname
        or query.is_supp_scene
        or query.collect_date_from
        or query.collect_date_to
        or query.public_date_from
        or query.public_date_to
        or query.create_time_from
        or query.create_time_to
    )


def _run(operation: Callable[[], Row]) -> Row:
    try:
        return {"state": "ready", "data": operation(), "message": ""}
    except DependencyUnavailableError:
        return {"state": "error", "data": None, "message": "精确总量查询超时或源库不可用，请稍后重试"}
    except Exception:  # 后台任务边界：记录异常并保留错误状态，避免无限轮询
        logger.exception("tender_count_failed")
        return {"state": "error", "data": None, "message": "精确总量查询失败，请联系管理员"}


def poll(key: str, operation: Callable[[], Row]) -> Row:
    with _lock:
        now = monotonic()
        entry = _jobs.get(key)
        if entry is not None:
            created, future = entry
            if not future.done():
                return {"state": "pending", "data": None, "message": "正在统计精确总量"}
            res = future.result()
            # 异常结果不毒化 300 秒，仅保留 3 秒避免瞬态错误导致 5 分钟无法自愈
            ttl = 3.0 if res.get("state") == "error" else get_settings().stats_cache_seconds
            if now - created < ttl:
                return res
            del _jobs[key]
        is_baseline = key == "totals" or key.startswith("baseline:")
        if not is_baseline and sum(not job.done() for _, job in _jobs.values()) >= _MAX_PENDING:
            return {"state": "error", "data": None, "message": "统计任务较多，请稍后重试"}
        executor = _totals_executor if key == "totals" else (_baseline_executor if is_baseline else _executor)
        _jobs[key] = (now, executor.submit(_run, operation))
        # 只移除已完成任务，防止仍在执行的相同查询被重复提交。
        for old_key in list(_jobs):
            if len(_jobs) <= _MAX_ENTRIES:
                break
            if _jobs[old_key][1].done():
                del _jobs[old_key]
        return {"state": "pending", "data": None, "message": "正在统计精确总量"}


def _totals() -> Row:
    with source_reader(counting=True) as reader:
        purchaser = statistics.totals(reader, "purchaser")
        winbid = statistics.totals(reader, "winbid")
    return {
        "purchaser": purchaser,
        "winbid": winbid,
        "total": purchaser + winbid,
        "as_of": utcnow().astimezone(BEIJING).isoformat(),
    }


def get_totals() -> Row:
    global _last_totals  # noqa: PLW0603  进程内保留最后一次成功快照，刷新失败不丢弃可用数据
    result = poll("totals", _totals)
    if result["state"] == "ready":
        _last_totals = result["data"]
    elif _last_totals is not None:
        return {**result, "data": _last_totals}
    return result


def _count(kind: Kind, query: ListQuery) -> Row:
    with source_reader(counting=True) as reader:
        total = records.count_records(reader, kind, query)
    if is_unfiltered(query):
        _baseline_counts[(kind, query.project_status)] = total
    return {"total": total}


def get_count(kind: Kind, query: ListQuery) -> Row:
    unfiltered = is_unfiltered(query)
    key = (
        f"baseline:{kind}:{query.project_status}"
        if unfiltered
        else f"{kind}:{query.model_dump_json(exclude={'page', 'page_size'})}"
    )
    res = poll(key, lambda: _count(kind, query))
    if unfiltered:
        baseline = _baseline_counts.get((kind, query.project_status))
        if baseline is None and query.project_status in ("", "all") and _last_totals and kind in _last_totals:
            baseline = int(_last_totals[kind])
            _baseline_counts[(kind, query.project_status)] = baseline
        if baseline is not None and (res.get("state") == "pending" or res.get("data") is None):
            return {"state": "ready", "data": {"total": baseline}, "message": ""}
    return res
