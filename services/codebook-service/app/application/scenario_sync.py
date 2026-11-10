"""政策解读里人工确认过的新增场景同步进行业场景码表，以及给解读行查已有场景的编码。由政策服务经内部接口调用。"""

from __future__ import annotations

from typing import Any

from platform_common.actors import Actor
from platform_common.clock import utcnow
from platform_common.errors import ApiError, ErrorCode
from platform_common.similarity import similarity_level
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.audit_emit import enqueue_event
from app.domain.fields import ENRICH_PENDING
from app.domain.models import SCENARIO_FIELDS, Scenario, content_hash
from app.domain.scenario_codes import NEW_MARK, CodeBook, Codes, ScenarioItem
from app.domain.scenario_similarity import ScenarioNodes
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

    每条：key、path（场景路径，到新的那一级为止）、industry_l1（新的一级场景跟同一个一级行业下的比），
    with_paths 为真时再给出这些一级行业下的全部场景路径（AI 找相似场景当参照）。
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
        item = {
            "key": key,
            "siblings": nodes.siblings(path, industries),
            "similar": similar,
            "industries": nodes.industries_of(path),
            "best_level": similarity_level(best),
        }
        if raw.get("with_paths"):
            item["industry_paths"] = nodes.paths_under(industries)
        out.append(item)
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
        enrich_status=ENRICH_PENDING,
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


NAME_MAX = 255
LEVELS = 3


def _apply_rename(rows: list[Scenario], level: int, old_name: str, new_name: str, caller: Actor) -> None:
    now = utcnow()
    seen_hashes: set[str] = set()
    for row in rows:
        setattr(row, f"scenario_l{level}_name", new_name)
        if row.scenario_tag == old_name:
            row.scenario_tag = new_name
        row.refresh_hash()
        digest = getattr(row, "content_hash", None)
        if digest:
            if digest in seen_hashes:
                raise ApiError(
                    "改名后会出现完全相同的场景记录，请先清理重复行",
                    code=ErrorCode.DUPLICATE,
                    http_status=409,
                )
            seen_hashes.add(digest)
        row.version += 1
        row.updated_at, row.updated_by_id, row.updated_by_name = now, caller.id, caller.name


async def rename(
    session: AsyncSession, caller: Actor, path: list[str], new_name: str, *, dry_run: bool
) -> dict[str, Any]:
    """把一个已有场景（path 的最后一级）改名，各行业、各客群下的行一起改；编码不变。dry_run 只数会改多少行。

    新增场景审核里「合并到已有场景、原场景改用新说法」时用。同一上级下已经有这个名字就拒绝，免得两个场景并成一个名。
    """

    names = tuple(str(name or "").strip() for name in path if str(name or "").strip())
    new_name = new_name.strip()
    if not names or len(names) > LEVELS:
        raise ApiError("要改名的场景路径不对", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if not new_name or len(new_name) > NAME_MAX or NEW_MARK.search(new_name):
        raise ApiError(
            f"新名称不能为空、最多 {NAME_MAX} 字、不能带「（新增）」", code=ErrorCode.VALIDATION_ERROR, http_status=422
        )
    if not dry_run and new_name != names[-1]:
        await repo.lock_scenario_codes(session)
    rows = await repo.rows_with_path(session, names, lock=not dry_run)
    if not rows:
        raise ApiError("码表里没有这个场景", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    if dry_run or new_name == names[-1]:
        return {"rows": len(rows)}
    if await repo.path_exists(session, (*names[:-1], new_name)):
        raise ApiError(f"同一上级下已经有「{new_name}」，不能改成这个名字", code=ErrorCode.DUPLICATE, http_status=409)
    _apply_rename(rows, len(names), names[-1], new_name, caller)
    await session.flush()
    await enqueue_event(
        session,
        event_type="codebook.scenario.renamed",
        actor=caller,
        extra={"path": " > ".join(names), "new_name": new_name, "rows": len(rows)},
    )
    return {"rows": len(rows)}
