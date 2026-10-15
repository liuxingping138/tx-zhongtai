"""worker 用的队列操作：认领排队任务、回收上个进程留下的运行中任务、写进程心跳。"""

from __future__ import annotations

from platform_common.clock import utcnow
from sqlalchemy.dialects.postgresql import insert

from app.core.database import SessionLocal
from app.domain.models import RUN_INTERRUPTED, WorkerHeartbeat
from app.repositories import batch_runs as repo

ORPHAN_MESSAGE = "执行进程重启，任务未完成；已跑完的部分可下载原始返回"


async def claim_next() -> str | None:
    async with SessionLocal() as session:
        run = await repo.claim_next(session, now=utcnow())
        await session.commit()
        return run.id if run else None


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
