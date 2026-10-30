"""worker 用的队列操作：认领排队任务、回收上个进程留下的运行中任务、写进程心跳。"""

from __future__ import annotations

from collections.abc import Collection
from datetime import timedelta
from typing import Any

from platform_common.clock import utcnow
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.domain.models import RUN_INTERRUPTED, RUN_SOURCE_MANUAL, WorkerHeartbeat
from app.repositories import batch_runs as repo

ORPHAN_MESSAGE = "执行进程重启，任务未完成；已跑完的部分可下载原始返回"
# leader 每 10 秒写一次心跳；超过这么久没写，就当执行进程不在（健康检查同一口径）。
WORKER_STALE = timedelta(seconds=60)
# 页面发起的批量任务最多占到「总执行位 - 1」，留一个给样本试跑和定时打标：
# 几个大任务占满后，十条的试跑、每天的打标不用排几个小时。
BULK_SOURCES = (RUN_SOURCE_MANUAL,)


def bulk_limit(total: int) -> int:
    """批量任务能占几个执行位。只有一个执行位时没法留，照旧先来先跑。"""

    return total - 1 if total > 1 else total


async def claim_next(
    *, exclude_sources: Collection[str] = (), exclude_ids: Collection[str] = ()
) -> tuple[str, str] | None:
    """认领一条排队任务，返回 (任务ID, 来源)。"""

    async with SessionLocal() as session:
        run = await repo.claim_next(session, now=utcnow(), exclude_sources=exclude_sources, exclude_ids=exclude_ids)
        await session.commit()
        return (run.id, run.source) if run else None


async def worker_status(session: AsyncSession) -> dict[str, Any]:
    """页面用：执行进程在不在。不在时排队的任务不会开始，页面要说出来，不能让人一直等「排队中」。"""

    seen_at = await repo.worker_seen_at(session)
    return {"online": seen_at is not None and utcnow() - seen_at < WORKER_STALE}


async def recover_orphans() -> int:
    """只有拿到 leader 锁的进程才调用：此时还处于运行中的任务，执行它的进程一定已经不在了。"""

    async with SessionLocal() as session:
        ids = await repo.running_ids(session)
        for run_id in ids:
            await repo.update_fields(
                session,
                run_id,
                {"status": RUN_INTERRUPTED, "error_message": ORPHAN_MESSAGE, "cancel_requested": False},
            )
        await session.commit()
        return len(ids)


async def beat() -> None:
    now = utcnow()
    async with SessionLocal() as session:
        await session.execute(
            insert(WorkerHeartbeat)
            .values(id=1, seen_at=now)
            .on_conflict_do_update(index_elements=["id"], set_={"seen_at": now})
        )
        await session.commit()
