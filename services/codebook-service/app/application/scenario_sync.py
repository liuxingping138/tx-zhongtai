"""政策解读里人工确认过的新增场景同步进行业场景码表，以及给解读行查已有场景的编码。由政策服务经内部接口调用。"""

from __future__ import annotations

from typing import Any

from platform_common.actors import Actor
from platform_common.clock import utcnow
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.audit_emit import enqueue_event
from app.domain.models import SCENARIO_FIELDS, Scenario, content_hash
from app.domain.scenario_codes import CodeBook, Codes, ScenarioItem
from app.domain.scenario_similarity import ScenarioNodes, similarity_level
from app.repositories import code_tables as repo


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
    """只查不建：六级名称对上已有场景，或按一级行业对上通用场景，才返回编码。

    同时给出比对结果（kind、new_level，见 scenario_codes.classify）：政策服务据此把新增场景归成待审的候选。
    """

    book = CodeBook.from_rows(await repo.scenario_codes(session))
    out = []
    for raw in items:
        found = book.classify(_item(raw))
        out.append(_codes_out(str(raw.get("key") or ""), found.codes, kind=found.kind, new_level=found.new_level))
    return out


def _path(raw: dict[str, Any]) -> tuple[str, ...]:
    names = [str(name or "").strip() for name in raw.get("path") or []][:3]
    while names and not names[-1]:
        names.pop()
    return tuple(names)


async def context(session: AsyncSession, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """新增场景审核的码表上下文：要挂的位置下已有的场景、字面最像的已有场景、这个场景已经挂在哪些行业下。

    每条：key、path（场景路径，到新的那一级为止）、industry_l1（新的一级场景跟同一个一级行业下的比）。
    """

    nodes = ScenarioNodes.from_rows(await repo.scenario_nodes(session))
    out: list[dict[str, Any]] = []
    for raw in items:
        path = _path(raw)
        key = str(raw.get("key") or "")
        if not path:
            out.append({"key": key, "siblings": [], "similar": [], "industries": [], "best_level": "无"})
            continue
        industries = [str(name) for name in raw.get("industry_l1") or [] if name]
        similar = nodes.similar(path, industries)
        best = float(similar[0]["score"]) if similar else 0.0
        out.append(
            {
                "key": key,
                "siblings": nodes.siblings(path, industries),
                "similar": similar,
                "industries": nodes.industries_of(path),
                "best_level": similarity_level(best),
            }
        )
    return out


def _new_row(item: ScenarioItem, codes: Codes, caller: Actor, source_policy: str) -> Scenario:
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
    )
    now = utcnow()
    return Scenario(
        content_hash=content_hash(values, SCENARIO_FIELDS),
        is_new_scenario="是",
        source_policy=source_policy[:500],
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
            session.add(_new_row(item, codes, caller, str(raw.get("source_policy") or "")))
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
