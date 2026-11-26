"""磁盘留存清理：定期删除超期的定时打标产物目录和超出历史上限的样本试跑目录。

只清理盘上实际存在且数据库明确已结束（非 queued/running/stopping）的任务目录：
- 数据库中还没有记录的目录（例如 pipeline_runs.create 正在写快照）绝不碰；
- 仍在排队或运行中的任务绝不碰；
- 保留数据库记录，费用账单和历史统计不受影响。
"""

from __future__ import annotations

import logging
from datetime import timedelta

import anyio
from platform_common.clock import utcnow
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.sample_runs import HISTORY_MAX
from app.core import storage
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.domain.models import ACTIVE_STATUSES, RUN_SOURCE_PIPELINE, RUN_SOURCE_SAMPLE, BatchRun
from app.repositories import batch_runs as repo

logger = logging.getLogger("ai.retention")
_DB_CHUNK = 500


def _disk_run_ids() -> list[str]:
    runs_root = storage.data_dir() / "runs"
    if not runs_root.is_dir():
        return []
    return [entry.name for entry in runs_root.iterdir() if entry.is_dir() and storage.ID_PATTERN.fullmatch(entry.name)]


def _remove_dirs(run_ids: list[str]) -> int:
    removed = 0
    for run_id in run_ids:
        target = storage.run_dir(run_id)
        if not target.is_dir():
            continue
        try:
            storage.remove_tree(target)
            removed += 1
        except OSError:
            logger.warning("retention_remove_failed run=%s", run_id, exc_info=True)
    return removed


async def _excess_sample_ids(session: AsyncSession, old_samples: list[BatchRun]) -> list[str]:
    if not old_samples:
        return []
    keep_by_prompt: dict[str, set[str]] = {}
    for prompt_id in {item.prompt_id for item in old_samples}:
        recent, _ = await repo.sample_history(session, prompt_id, limit=HISTORY_MAX)
        keep_by_prompt[prompt_id] = {row.id for row in recent}
    return [
        item.id
        for item in old_samples
        if item.deleted_at is not None or item.id not in keep_by_prompt.get(item.prompt_id, set())
    ]


async def prune_expired_runs() -> int:
    """清理超期的已完成流水线目录与超上限的旧样本试跑目录，返回清理的目录数。"""

    disk_ids = await anyio.to_thread.run_sync(_disk_run_ids)
    if not disk_ids:
        return 0
    settings = get_settings()
    now = utcnow()
    pipeline_cutoff = now - timedelta(days=max(settings.pipeline_retention_days, 1))
    sample_cutoff = now - timedelta(days=max(settings.sample_retention_days, 1))
    doomed: list[str] = []
    old_samples: list[BatchRun] = []

    async with SessionLocal() as session:
        for start in range(0, len(disk_ids), _DB_CHUNK):
            for item in await repo.by_ids(session, disk_ids[start : start + _DB_CHUNK]):
                if item.status in ACTIVE_STATUSES:
                    continue
                ended_at = item.finished_at or item.created_at
                if item.source == RUN_SOURCE_PIPELINE and ended_at < pipeline_cutoff:
                    doomed.append(item.id)
                elif item.source == RUN_SOURCE_SAMPLE and ended_at < sample_cutoff:
                    old_samples.append(item)
        doomed.extend(await _excess_sample_ids(session, old_samples))

    if not doomed:
        return 0
    return await anyio.to_thread.run_sync(_remove_dirs, doomed)
