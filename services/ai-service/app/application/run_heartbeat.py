"""任务执行中长操作期间的心跳：任务超过 AI_BATCH_STALE_SECONDS 没心跳会被纠正成「中断」。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

from platform_common.clock import utcnow

from app.core.database import SessionLocal
from app.repositories import batch_runs as repo

logger = logging.getLogger("ai.batch")
# 开始前读回原始返回、收尾时生成结果表这些长操作期间，隔这么久写一次心跳。
BEAT_SECONDS = 20.0


@contextlib.asynccontextmanager
async def beating(run_id: str) -> AsyncIterator[None]:
    """长操作期间照写心跳。大任务重跑要重新解析 Excel、把整份原始返回读一遍，收尾要生成结果表、重拼失败行的提问，
    十万行的任务都可能超过一分半：原来这期间没心跳，被纠正成「中断」后执行协程发现任务已不在运行就自己停了，
    再点重跑还是同样结局。"""

    async def beat() -> None:
        while True:
            await asyncio.sleep(BEAT_SECONDS)
            try:
                async with SessionLocal() as session:
                    await repo.update_if_running(session, run_id, {"heartbeat_at": utcnow()})
                    await session.commit()
            except Exception:
                logger.exception("batch_run_beat_failed run=%s", run_id)

    task = asyncio.create_task(beat())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
