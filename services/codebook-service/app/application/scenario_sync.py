"""政策解读里人工确认过的新增场景同步进行业场景码表，以及给解读行查已有场景的编码。由政策服务经内部接口调用。"""

from __future__ import annotations

from typing import Any

from platform_common.actors import Actor
from platform_common.clock import utcnow
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.audit_emit import enqueue_event
from app.domain.models import SCENARIO_FIELDS, Scenario, content_hash
from app.domain.scenario_codes import CodeBook, Codes, ScenarioItem
from app.repositories import code_tables as repo

SOURCE_LABEL = "政策解读新增"


def _item(raw: dict[str, Any]) -> ScenarioItem:
    def names(*keys: str) -> tuple[str, str, str]:
        a, b, c = (str(raw.get(key) or "").strip() for key in keys)
        return a, b, c

    return ScenarioItem(
        industry=names("industry_l1", "industry_l2", "industry_l3"),
        scenario=names("scenario_l1_name", "scenario_l2_name", "scenario_l3_name"),
    )


def _codes_out(key: str, codes: Codes | None, **extra: Any) -> dict[str, Any]:
    return {
        "key": key,
        "industry_code": codes.industry_code if codes else "",
        "scenario_code": codes.scenario_code if codes else "",
        "industry_scenario_code": codes.industry_scenario_code if codes else "",
        **extra,
    }


async def lookup(session: AsyncSession, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """只查不建：六级名称完全对上已有场景才返回编码。"""

    book = CodeBook.from_rows(await repo.scenario_codes(session))
    return [_codes_out(str(raw.get("key") or ""), book.lookup(_item(raw))) for raw in items]


def _new_row(item: ScenarioItem, codes: Codes, caller: Actor, source_note: str) -> Scenario:
    values = dict.fromkeys(SCENARIO_FIELDS, "")
    values.update(
        industry_scenario_code=codes.industry_scenario_code,
        industry_code=codes.industry_code,
        industry_l1=item.industry[0],
        industry_l2=item.industry[1],
        industry_l3=item.industry[2],
        scenario_code=codes.scenario_code,
        scenario_l1_name=item.scenario[0],
        scenario_l2_name=item.scenario[1],
        scenario_l3_name=item.scenario[2],
        scenario_source=SOURCE_LABEL,
        scenario_l3_desc=source_note[:500],
    )
    now = utcnow()
    return Scenario(
        content_hash=content_hash(values, SCENARIO_FIELDS),
        version=1,
        created_at=now,
        created_by_id=caller.id,
        created_by_name=caller.name,
        updated_at=now,
        updated_by_id=caller.id,
        updated_by_name=caller.name,
        **values,
    )


async def sync(session: AsyncSession, caller: Actor, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """逐条分配编码并写入；已有同名同路径的直接返回原编码。单条出错（行业不在码表等）不影响其他条。"""

    await repo.lock_scenario_codes(session)
    book = CodeBook.from_rows(await repo.scenario_codes(session))
    results: list[dict[str, Any]] = []
    created = 0
    for raw in items:
        key = str(raw.get("key") or "")
        item = _item(raw)
        try:
            codes, is_new = book.assign(item)
        except ValueError as exc:
            results.append(_codes_out(key, None, created=False, error=str(exc)))
            continue
        if is_new:
            session.add(_new_row(item, codes, caller, str(raw.get("source_note") or "")))
            created += 1
        results.append(_codes_out(key, codes, created=is_new, error=""))
    await session.flush()
    await enqueue_event(
        session,
        event_type="codebook.scenario.synced",
        actor=caller,
        extra={"items": len(items), "created": created},
    )
    return results
