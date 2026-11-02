"""新增场景归集、套用决定共用的底层操作：取一行的六级名称、去码表比对、重算关联主键、把行改成另一个场景的说法。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common import internal_clients
from app.policy.application.region import make_relation_key
from app.policy.domain.candidates import KIND_NEW, Names, ScenarioCandidate
from app.policy.domain.fields import SCENARIO_CODE_FIELDS, SCENARIO_NAME_FIELDS, SCENARIO_STATE_DUPLICATE
from app.policy.domain.models import Interpretation
from app.policy.repositories import scenario_candidates as repo

LOOKUP_CHUNK = 5000
Pair = tuple[Names, Names]


def row_names(row: Interpretation) -> Pair:
    values = [str(getattr(row, field) or "").strip() for field in SCENARIO_NAME_FIELDS]
    return (values[0], values[1], values[2]), (values[3], values[4], values[5])


def names_payload(industry: Names, scenario: Names) -> dict[str, str]:
    return dict(zip(SCENARIO_NAME_FIELDS, (*industry, *scenario), strict=True))


def set_codes(row: Interpretation, codes: dict[str, Any] | None) -> None:
    for field in SCENARIO_CODE_FIELDS:
        setattr(row, field, str((codes or {}).get(field) or ""))


def system_touch(row: Interpretation) -> None:
    """系统改了这一行：只加版本号（开着编辑框的人保存时会提示被改过），更新时间和操作人不动。"""

    row.version += 1


async def lookup(pairs: list[Pair]) -> dict[Pair, dict[str, Any]]:
    """一组行业场景名称去码表比对，同样的名称只问一次。"""

    unique = list(dict.fromkeys(pairs))
    out: dict[Pair, dict[str, Any]] = {}
    for start in range(0, len(unique), LOOKUP_CHUNK):
        chunk = unique[start : start + LOOKUP_CHUNK]
        items = [{"key": str(i), **names_payload(*pair)} for i, pair in enumerate(chunk)]
        found = await internal_clients.codebook("POST", "/internal/v1/scenarios/lookup", json={"items": items})
        by_key = {str(item.get("key")): item for item in found}
        out.update({pair: by_key.get(str(i), {}) for i, pair in enumerate(chunk)})
    return out


async def rekey(session: AsyncSession, rows: list[Interpretation]) -> None:
    """按现在的编码、名称重算关联主键。撞上同一政策另一行（同场景、同机会类型）的标「重复」，留着原主键，不删。

    本批行原来的主键也算占用：一行换走的主键不让本批另一行马上接过去，免得按更新顺序撞上唯一约束。
    """

    planned = {
        row.id: make_relation_key(
            row.policy_uid,
            row.industry_scenario_code,
            row.opportunity_type,
            [str(getattr(row, field) or "") for field in SCENARIO_NAME_FIELDS],
        )
        for row in rows
    }
    changing = [key for row in rows if (key := planned[row.id]) != row.relation_key]
    if not changing:
        return
    taken = await repo.taken_relation_keys(session, changing, exclude={row.id for row in rows})
    taken.update(row.relation_key for row in rows)
    for row in rows:
        key = planned[row.id]
        if key == row.relation_key:
            continue
        if key in taken:
            row.scenario_state = SCENARIO_STATE_DUPLICATE
            continue
        taken.add(key)
        row.relation_key = key


MAX_HOPS = 5


async def final_candidate(session: AsyncSession, candidate: ScenarioCandidate) -> ScenarioCandidate:
    """并到别的场景的说法，顺着找到最后归到的那个场景（最多跳几次，防止数据出错时绕圈）。"""

    current = candidate
    for _ in range(MAX_HOPS):
        if current.merged_into is None:
            return current
        nxt = await repo.get_for_update(session, current.merged_into)
        if nxt is None:
            return current
        current = nxt
    return current


def move_rows(rows: list[Interpretation], source: ScenarioCandidate, target: ScenarioCandidate) -> None:
    """被并入的说法换成目标场景的说法：到新的那一级为止换成目标的路径，更下级的保留。"""

    for row in rows:
        _, scenario = row_names(row)
        tail = [name for name in scenario[source.new_level :] if name] if source.kind == KIND_NEW else []
        names = [*[name for name in target.path() if name], *tail, "", "", ""][:3]
        row.scenario_l1_name, row.scenario_l2_name, row.scenario_l3_name = names
        row.candidate_id = target.id
