"""新增场景列表上勾选几个一起驳回、一起合并到同一个已有场景。逐个做决定，跳过的写明原因。"""

from __future__ import annotations

import uuid
from typing import Any

from platform_common.actors import Actor
from platform_common.errors import ApiError
from sqlalchemy.ext.asyncio import AsyncSession

from app.policy.application import scenario_decisions
from app.policy.application.scenario_merging import display_name
from app.policy.repositories import scenario_candidates as repo


async def _each(session: AsyncSession, items: list[tuple[uuid.UUID, int]], action: Any) -> dict[str, Any]:
    """逐个做决定，各自一个保存点：一个失败（被人改过、已经决定过）不影响其他的，跳过的写明原因。"""

    done, skipped = 0, []
    for candidate_id, version in items:
        try:
            async with session.begin_nested():
                await action(candidate_id, version)
            done += 1
        except ApiError as exc:
            candidate = await repo.get(session, candidate_id)
            name = display_name(candidate) if candidate else str(candidate_id)
            skipped.append({"name": name, "reason": exc.message})
    return {"done": done, "skipped": skipped}


async def batch_reject(
    session: AsyncSession, actor: Actor, items: list[tuple[uuid.UUID, int]], *, reason: str, note: str
) -> dict[str, Any]:
    async def one(candidate_id: uuid.UUID, version: int) -> None:
        await scenario_decisions.reject(session, actor, candidate_id, version=version, reason=reason, note=note)

    return await _each(session, items, one)


async def batch_merge(
    session: AsyncSession, actor: Actor, items: list[tuple[uuid.UUID, int]], *, target: list[str]
) -> dict[str, Any]:
    async def one(candidate_id: uuid.UUID, version: int) -> None:
        await scenario_decisions.merge(session, actor, candidate_id, version=version, target=target)

    return await _each(session, items, one)
