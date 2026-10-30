"""政策解读里人工确认过的新增场景同步进行业场景码表。

只同步「是否新增场景 = 是」且「数据状态 = 人工验证」、还没同步过的行。编码由码表服务按现有规则生成
（各级号取全局最大号 + 1，已有的上级沿用），回填到解读行；同一场景重复同步返回原编码，不会在码表里重复建。

回填编码后关联主键跟着换成编码形式（政策 + 行业场景编码 + 机会类型）：不换的话，之后导入、重新解读按编码算出的主键
对不上，会再插一条重复的。换完和这条政策已有的另一行撞上，说明两行讲的是同一件事，这一行不回填、写进失败清单让人处理，
不替人删数据。
"""

from __future__ import annotations

from typing import Any

from platform_common.actors import Actor
from platform_common.clock import utcnow
from sqlalchemy.ext.asyncio import AsyncSession

from app.common import internal_clients
from app.common.audit_emit import enqueue_event
from app.policy.application.region import make_relation_key
from app.policy.domain.fields import SCENARIO_NAME_FIELDS
from app.policy.domain.models import Interpretation
from app.policy.repositories import interpretations as repo

MAX_ITEMS = 5000
SAME_ROW = (
    "这条政策已有同一场景、同一机会类型的解读记录，编码没有回填：请核对这两条，改掉其中一条的场景或机会类型后再同步"
)


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
        return {"synced": 0, "created": 0, "failed": [], "failed_total": 0}
    results = await internal_clients.codebook(
        "POST",
        "/internal/v1/scenarios/sync",
        json={"items": [_item(row) for row in rows], "caller_name": actor.name, "caller_id": actor.id},
    )
    by_key = {str(item["key"]): item for item in results}
    now = utcnow()
    synced = created = 0
    failed: list[dict[str, str]] = []
    planned: list[tuple[Interpretation, dict[str, Any], str]] = []
    for row in rows:
        result = by_key.get(str(row.id))
        if result is None or result.get("error"):
            failed.append(
                {"policy_title": row.policy_title, "reason": str((result or {}).get("error") or "码表服务没有返回结果")}
            )
            continue
        key = make_relation_key(row.policy_uid, str(result["industry_scenario_code"]), row.opportunity_type)
        planned.append((row, result, key))
    taken = await repo.existing_relation_keys(session, [key for row, _, key in planned if key != row.relation_key])
    for row, result, key in planned:
        if key != row.relation_key and key in taken:
            failed.append({"policy_title": row.policy_title, "reason": SAME_ROW})
            continue
        taken.add(key)
        row.relation_key = key
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
    # 清单只带前 50 条（页面列前 10 条），总数单独给：超过 50 条时原来提示「以下 50 条没有同步」，数字偏小。
    return {"synced": synced, "created": created, "failed": failed[:50], "failed_total": len(failed)}
