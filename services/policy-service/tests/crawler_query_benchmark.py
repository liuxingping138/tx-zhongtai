"""只读爬虫查询基准：在回填完成后运行，最多 5 并发，不调用采集源或导出。

复制到容器后运行：.venv/bin/python /tmp/crawler_query_benchmark.py
输出仅包含数量与时延，不输出业务记录和凭据；不代表生产容量上限。
"""

from __future__ import annotations

import asyncio
import json
import math
import statistics
import sys
from collections import defaultdict
from collections.abc import Awaitable, Callable
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path.cwd()))

from app.core.database import SessionLocal, engine
from app.crawler.application import crawler as service
from app.crawler.repositories import crawler as repo

SAMPLES_PER_CASE = 8
TIMEOUT_SECONDS = 20

Query = Callable[[AsyncSession], Awaitable[None]]


def build_cases(total: int, sample: dict[str, Any]) -> dict[str, Query]:
    """每个用例一次只读查询，附带最基本的结果核对，防止测到的是空结果。"""

    async def overview_90d(session: AsyncSession) -> None:
        assert len((await service.overview(session, trend_days=90))["trend"]) == 90

    async def first_page(session: AsyncSession) -> None:
        assert (await service.list_tasks(session, filters={}, page=1, page_size=20))["total"] == total

    async def filtered_page(session: AsyncSession) -> None:
        await service.list_tasks(session, filters={"health_status": "broken"}, page=1, page_size=20)

    async def options(session: AsyncSession) -> None:
        assert (await service.list_options(session))["options"]["health_status"]["items"]

    async def detail_90d(session: AsyncSession) -> None:
        result = await service.task_detail(
            session, site_code="", site_key=sample["site_key"], tag=sample["tag"], days=90
        )
        assert len(result["series"]) == 90

    return {
        "overview_90d": overview_90d,
        "first_page": first_page,
        "filtered_page": filtered_page,
        "options": options,
        "detail_90d": detail_90d,
    }


async def run_query(query: Query) -> None:
    async with SessionLocal() as session:
        await asyncio.wait_for(query(session), timeout=TIMEOUT_SECONDS)


def summarize(name: str, durations: list[float]) -> dict[str, Any]:
    values = sorted(durations)
    return {
        "query": name,
        "samples": len(values),
        "p50_ms": round(statistics.median(values), 1),
        "p95_ms": round(values[math.ceil(0.95 * len(values)) - 1], 1),
        "max_ms": round(max(values), 1),
    }


async def run_at(concurrency: int, cases: dict[str, Query]) -> dict[str, Any]:
    semaphore = asyncio.Semaphore(concurrency)
    durations: dict[str, list[float]] = defaultdict(list)

    async def timed(name: str) -> None:
        async with semaphore:
            started = perf_counter()
            await run_query(cases[name])
            durations[name].append((perf_counter() - started) * 1000)

    started = perf_counter()
    await asyncio.gather(*(timed(name) for _ in range(SAMPLES_PER_CASE) for name in cases))
    elapsed = perf_counter() - started
    queries = SAMPLES_PER_CASE * len(cases)
    return {
        "concurrency": concurrency,
        "queries": queries,
        "elapsed_seconds": round(elapsed, 2),
        "throughput_per_second": round(queries / elapsed, 2),
        "errors": 0,
        "results": [summarize(name, durations[name]) for name in cases],
    }


async def main() -> None:
    async with SessionLocal() as session:
        pending = await repo.pending_identity_backfill(session)
        assert pending["days"] == 0, "先完成历史回填，再执行查询基准"
        first = await service.list_tasks(session, filters={}, page=1, page_size=20)
        assert first["items"], "需要真实任务数据"
    cases = build_cases(first["total"], first["items"][0])
    # 先串行各跑一遍预热，再计时。
    for query in cases.values():
        await run_query(query)
    report = {
        "task_count": first["total"],
        "scope": "application queries with real PostgreSQL; excludes HTTP/auth overhead",
        "runs": [await run_at(concurrency, cases) for concurrency in (1, 5)],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
