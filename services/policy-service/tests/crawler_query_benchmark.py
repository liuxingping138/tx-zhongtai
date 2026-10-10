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
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path.cwd()))

from app.core.database import SessionLocal, engine
from app.crawler.application import crawler as service
from app.crawler.repositories import crawler as repo


async def main() -> None:
    async with SessionLocal() as session:
        pending = await repo.pending_identity_backfill(session)
        assert pending["days"] == 0, "先完成历史回填，再执行查询基准"
        first = await service.list_tasks(session, filters={}, page=1, page_size=20)
        assert first["items"], "需要真实任务数据"
        sample = first["items"][0]
        total = first["total"]

    async def query(name: str) -> None:
        async with SessionLocal() as session:
            if name == "overview_90d":
                result = await service.overview(session, trend_days=90)
                assert len(result["trend"]) == 90
            elif name == "first_page":
                result = await service.list_tasks(session, filters={}, page=1, page_size=20)
                assert result["total"] == total
            elif name == "filtered_page":
                await service.list_tasks(session, filters={"health_status": "broken"}, page=1, page_size=20)
            elif name == "options":
                result = await service.list_options(session)
                assert result["options"]["health_status"]["items"]
            elif name == "detail_90d":
                result = await service.task_detail(
                    session, site_code="", site_key=sample["site_key"], tag=sample["tag"], days=90
                )
                assert len(result["series"]) == 90
            else:
                raise AssertionError(name)

    cases = ["overview_90d", "first_page", "filtered_page", "options", "detail_90d"]
    for case in cases:
        await asyncio.wait_for(query(case), timeout=20)

    async def sample_one(case, semaphore, durations) -> None:
        async with semaphore:
            started = perf_counter()
            await asyncio.wait_for(query(case), timeout=20)
            durations[case].append((perf_counter() - started) * 1000)

    report = {
        "task_count": total,
        "scope": "application queries with real PostgreSQL; excludes HTTP/auth overhead",
        "runs": [],
    }
    for concurrency in (1, 5):
        semaphore = asyncio.Semaphore(concurrency)
        durations = defaultdict(list)

        started = perf_counter()
        await asyncio.gather(*(sample_one(case, semaphore, durations) for _ in range(8) for case in cases))
        elapsed = perf_counter() - started
        results = []
        for case in cases:
            values = sorted(durations[case])
            results.append(
                {
                    "query": case,
                    "samples": len(values),
                    "p50_ms": round(statistics.median(values), 1),
                    "p95_ms": round(values[math.ceil(0.95 * len(values)) - 1], 1),
                    "max_ms": round(max(values), 1),
                }
            )
        report["runs"].append(
            {
                "concurrency": concurrency,
                "queries": 40,
                "elapsed_seconds": round(elapsed, 2),
                "throughput_per_second": round(40 / elapsed, 2),
                "errors": 0,
                "results": results,
            }
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
