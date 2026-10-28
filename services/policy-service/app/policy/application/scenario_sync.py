"""政策解读里人工确认过的新增场景同步进行业场景码表。

只同步「是否新增场景 = 是」且「数据状态 = 人工验证」、还没同步过的行。编码由码表服务按现有规则生成
（各级号取全局最大号 + 1，已有的上级沿用），回填到解读行；同一场景重复同步返回原编码，不会在码表里重复建。
"""

from __future__ import annotations

from typing import Any

from platform_common.actors import Actor
from platform_common.clock import utcnow
from sqlalchemy.ext.asyncio import AsyncSession

from app.common import internal_clients
from app.common.audit_emit import enqueue_event
from app.policy.domain.fields import SCENARIO_NAME_FIELDS
from app.policy.domain.models import Interpretation
from app.policy.repositories import interpretations as repo

MAX_ITEMS = 5000


async def pending(session: AsyncSession) -> dict[str, Any]:
    return {"pending": await repo.count_unsynced_new_scenarios(session)}


def _item(row: Interpretation) -> dict[str, str]:
    return {
        "key": str(row.id),
        **{level: getattr(row, level) for level in SCENARIO_NAME_FIELDS},
        "source_policy": row.policy_title[:500],
    }


async def sync(session: AsyncSession, actor: Actor) -> dict[str, Any]:
    rows = await repo.unsynced_new_scenarios(session, MAX_ITEMS)
    if not rows:
        return {"synced": 0, "created": 0, "failed": []}
    results = await internal_clients.codebook(
        "POST",
        "/internal/v1/scenarios/sync",
        json={"items": [_item(row) for row in rows], "caller_name": actor.name},
    )
    by_key = {str(item["key"]): item for item in results}
    now = utcnow()
    synced = created = 0
    failed: list[dict[str, str]] = []
    for row in rows:
        result = by_key.get(str(row.id))
        if result is None or result.get("error"):
            failed.append(
                {"policy_title": row.policy_title, "reason": str((result or {}).get("error") or "码表服务没有返回结果")}
            )
            continue
        row.industry_code = str(result["industry_code"])
        row.scenario_code = str(result["scenario_code"])
        row.industry_scenario_code = str(result["industry_scenario_code"])
        row.scenario_synced_at = now
        row.version += 1
        row.updated_at, row.updated_by_id, row.updated_by_name = now, actor.id, actor.name
        synced += 1
        created += 1 if result.get("created") else 0
    await enqueue_event(
        session,
        event_type="policy.interpretation.scenarios_synced",
        actor=actor,
        extra={"synced": synced, "created": created, "failed": len(failed)},
    )
    return {"synced": synced, "created": created, "failed": failed[:50]}
