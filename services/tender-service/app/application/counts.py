"""精确计数在有界线程池中执行；HTTP 轮询结果，不阻塞列表和正文。"""

from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from platform_common.clock import BEIJING, utcnow
from platform_common.errors import DependencyUnavailableError
from platform_common.logging_setup import get_logger

from app.core.config import get_settings
from app.core.source import Row, source_reader
from app.domain.fields import Kind, Status
from app.domain.queries import ListQuery
from app.repositories import records, statistics

logger = get_logger(__name__)


@dataclass
class _Job:
    created: float
    future: Future[Row]
    finished_at: float | None = None


_last_totals: Row | None = None
_baseline_counts: dict[tuple[Kind, Status], int] = {}
_totals_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tender-totals")
_baseline_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tender-baseline")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tender-count")
_closed_executors: set[ThreadPoolExecutor] = set()
_lock = Lock()
_jobs: OrderedDict[str, _Job] = OrderedDict()
_MAX_PENDING = 8
_MAX_ENTRIES = 128


def _normalize_status(status: Status) -> Status:
    return "all" if status in ("", "all") else status


def _is_baseline_key(key: str) -> bool:
    return key == "totals" or key.startswith("baseline:")


def _active_executor(is_totals: bool, is_baseline: bool) -> ThreadPoolExecutor:
    global _totals_executor, _baseline_executor, _executor  # noqa: PLW0603  进程重启或测试复启 lifespan 后按需重建线程池
    if is_totals:
        if _totals_executor in _closed_executors:
            _closed_executors.discard(_totals_executor)
            _totals_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tender-totals")
        return _totals_executor
    if is_baseline:
        if _baseline_executor in _closed_executors:
            _closed_executors.discard(_baseline_executor)
            _baseline_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tender-baseline")
        return _baseline_executor
    if _executor in _closed_executors:
        _closed_executors.discard(_executor)
        _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tender-count")
    return _executor


def shutdown_executors() -> None:
    with _lock:
        pools = (_totals_executor, _baseline_executor, _executor)
        _jobs.clear()
        for pool in pools:
            if isinstance(pool, ThreadPoolExecutor):
                _closed_executors.add(pool)
    for pool in pools:
        pool.shutdown(wait=False, cancel_futures=True)


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
            if not entry.future.done():
                return {"state": "pending", "data": None, "message": "正在统计精确总量"}
            finished_at = entry.finished_at if entry.finished_at is not None else now
            entry.finished_at = finished_at
            res = entry.future.result()
            # 异常结果不毒化 300 秒，仅保留 3 秒避免瞬态错误导致 5 分钟无法自愈；以完成时间为准避免长查询重试风暴
            ttl = 3.0 if res.get("state") == "error" else get_settings().stats_cache_seconds
            if now - finished_at < ttl:
                return res
            del _jobs[key]
        is_baseline = _is_baseline_key(key)
        active_user_jobs = sum(
            1 for job_key, item in _jobs.items() if not _is_baseline_key(job_key) and not item.future.done()
        )
        if not is_baseline and active_user_jobs >= _MAX_PENDING:
            return {"state": "error", "data": None, "message": "统计任务较多，请稍后重试"}
        executor = _active_executor(key == "totals", is_baseline)
        future = executor.submit(_run, operation)
        job = _Job(created=now, future=future)

        def _mark_done(_fut: Future[Row], target: _Job = job) -> None:
            if target.finished_at is None:
                target.finished_at = monotonic()

        future.add_done_callback(_mark_done)
        _jobs[key] = job
        # 只移除已完成任务，防止仍在执行的相同查询被重复提交。
        for old_key in list(_jobs):
            if len(_jobs) <= _MAX_ENTRIES:
                break
            if _jobs[old_key].future.done():
                del _jobs[old_key]
        return {"state": "pending", "data": None, "message": "正在统计精确总量"}


def _totals() -> Row:
    global _last_totals  # noqa: PLW0603  后台预热完成时立即回填最新快照，供统计与无条件计数共享
    with source_reader(counting=True) as reader:
        purchaser = statistics.totals(reader, "purchaser")
        purchaser_passed = statistics.totals_passed(reader, "purchaser")
        winbid = statistics.totals(reader, "winbid")
        winbid_passed = statistics.totals_passed(reader, "winbid")
    snapshot: Row = {
        "purchaser": purchaser,
        "purchaser_passed": purchaser_passed,
        "winbid": winbid,
        "winbid_passed": winbid_passed,
        "total": purchaser + winbid,
        "as_of": utcnow().astimezone(BEIJING).isoformat(),
    }
    with _lock:
        _last_totals = snapshot
    return snapshot


def get_totals() -> Row:
    global _last_totals  # noqa: PLW0603  进程内保留最后一次成功快照，刷新失败不丢弃可用数据
    result = poll("totals", _totals)
    with _lock:
        if result["state"] == "ready" and result["data"] is not None:
            _last_totals = result["data"]
        elif _last_totals is not None:
            return {**result, "data": _last_totals}
    return result


def _count(kind: Kind, query: ListQuery) -> Row:
    with source_reader(counting=True) as reader:
        total = records.count_records(reader, kind, query)
    if is_unfiltered(query):
        norm_status = _normalize_status(query.project_status)
        with _lock:
            _baseline_counts[(kind, norm_status)] = total
    return {"total": total}


def get_count(kind: Kind, query: ListQuery) -> Row:
    unfiltered = is_unfiltered(query)
    norm_status = _normalize_status(query.project_status)
    normalized = query.model_copy(update={"project_status": norm_status})
    key = (
        f"baseline:{kind}:{norm_status}"
        if unfiltered
        else f"{kind}:{normalized.model_dump_json(exclude={'page', 'page_size'})}"
    )
    res = poll(key, lambda: _count(kind, query))
    if unfiltered:
        with _lock:
            baseline = _baseline_counts.get((kind, norm_status))
            if baseline is None and norm_status == "all" and _last_totals and kind in _last_totals:
                baseline = int(_last_totals[kind])
                _baseline_counts[(kind, norm_status)] = baseline
        if baseline is not None and (res.get("state") == "pending" or res.get("data") is None):
            return {"state": "ready", "data": {"total": baseline}, "message": ""}
    return res
