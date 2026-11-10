"""新增场景：解读行和码表比对、归成候选，候选的决定套用到行上，以及人做决定的几条规则。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from platform_common.actors import Actor
from platform_common.errors import ApiError

from app.common import internal_clients
from app.policy.application import scenario_decisions, scenario_engine
from app.policy.application.region import make_relation_key
from app.policy.domain import candidates as domain
from app.policy.domain.candidates import ScenarioCandidate
from app.policy.domain.fields import SCENARIO_NAME_FIELDS
from app.policy.domain.models import Interpretation
from app.policy.repositories import scenario_candidates as repo

NOW = datetime(2026, 11, 2, tzinfo=UTC)
AIR = ("交通行业", "交通运输、仓储和邮政业", "航空")
HEALTH = ("医卫行业", "卫生", "卫生")
ROAD = ("交通行业", "交通运输、仓储和邮政业", "道路运输")
TARGET = ("智慧交通工程建设", "交通工程建设信息化", "")
# 码表里有的：行业 + 场景 → 场景编码
CODEBOOK = {
    (AIR, ("智慧航空", "智慧空侧", "行李自动化")): "172461199000",
    (ROAD, TARGET): "300400000000",
}
INDUSTRY_CODES = {AIR: "01010600", ROAD: "01010300", HEALTH: "03010100", ("重要客户服务二部", "", ""): "06000000"}
ACTOR = Actor(id="u1", name="张三")


def _verdict(industry: tuple[str, ...], scenario: tuple[str, ...]) -> dict[str, Any]:
    code = CODEBOOK.get((industry, scenario))
    if code:
        return {"kind": "exists", "new_level": 0, "industry_code": INDUSTRY_CODES[industry], "scenario_code": code}
    if industry not in INDUSTRY_CODES:
        return {"kind": "bad_industry", "new_level": 0}
    if scenario == TARGET:
        return {"kind": "association", "new_level": 0}
    if scenario[0] == "中医药数智化":
        return {"kind": "new", "new_level": 1}
    if scenario[0] == "智慧航空" and scenario[1] not in ("智慧空侧",):
        return {"kind": "new", "new_level": 2}
    return {"kind": "invalid", "new_level": 0}


class Codebook:
    def __init__(self) -> None:
        self.synced: list[dict[str, Any]] = []

    async def __call__(self, _method: str, path: str, **kwargs: Any) -> list[dict[str, Any]]:
        items = kwargs["json"]["items"]
        if path.endswith("/context"):
            return [
                {"key": item["key"], "similar": [{"path": list(TARGET[:2]), "score": 0.7}], "best_level": "高"}
                for item in items
            ]
        out = []
        for item in items:
            industry = (item["industry_l1"], item["industry_l2"], item["industry_l3"])
            scenario = (item["scenario_l1_name"], item["scenario_l2_name"], item["scenario_l3_name"])
            verdict = _verdict(industry, scenario)
            if path.endswith("/sync"):
                self.synced.append(item)
                # 已有的沿用编码；挂到新行业的沿用那个场景在别的行业下的编号；全新的按规则分配一个新号
                same = [code for (_, path), code in CODEBOOK.items() if path == scenario]
                code = verdict.get("scenario_code") or (same[0] if same else "248581000000")
                verdict = {"industry_code": INDUSTRY_CODES[industry], "scenario_code": code, "error": ""}
            out.append({"key": item["key"], **verdict})
        for item in out:
            if item.get("scenario_code"):
                item["industry_scenario_code"] = item["industry_code"] + item["scenario_code"]
        return out


class Session:
    async def flush(self) -> None:
        return None


def _row(industry: tuple[str, str, str], scenario: tuple[str, str, str], **extra: Any) -> Interpretation:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "policy_uid": extra.pop("policy_uid", "p1"),
        "policy_title": "某政策",
        "opportunity_type": "TO_B",
        "industry_code": "",
        "scenario_code": "",
        "industry_scenario_code": "",
        "is_new_scenario": "是",
        "new_scenario_level": "二级场景",
        "remark": "",
        "scenario_state": "",
        "candidate_id": None,
        "scenario_synced_at": None,
        "version": 1,
        "created_at": NOW,
        "updated_at": NOW,
        **dict(zip(("industry_l1", "industry_l2", "industry_l3"), industry, strict=True)),
        **dict(zip(("scenario_l1_name", "scenario_l2_name", "scenario_l3_name"), scenario, strict=True)),
        **extra,
    }
    row = Interpretation(**values)
    row.relation_key = make_relation_key(
        row.policy_uid, row.industry_scenario_code, row.opportunity_type, [*industry, *scenario]
    )
    return row


def _candidate(**spec: Any) -> ScenarioCandidate:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "status": domain.STATUS_PENDING,
        "version": 1,
        "first_seen_at": NOW,
        "last_seen_at": NOW,
        "created_at": NOW,
        "updated_at": NOW,
        "row_count": 0,
        "policy_count": 0,
        "industry_count": 0,
        "similar_score": 0.0,
        "decided_at": None,
        **dict.fromkeys(repo._TEXT_DEFAULTS, ""),
        **spec,
    }
    return ScenarioCandidate(**values)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(candidates={}, rows=[], taken=set(), codebook=Codebook(), events=[])

    async def ensure(_session: Any, specs: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
        for spec in specs:
            state.candidates.setdefault(spec["key"], _candidate(**spec))
        return {spec["key"]: state.candidates[spec["key"]] for spec in specs}

    async def taken(_session: Any, keys: list[str], exclude: set[Any]) -> set[str]:
        return {key for key in keys if key in state.taken}

    async def stats(_session: Any, ids: list[Any]) -> dict[Any, Any]:
        return {
            cid: (sum(1 for row in state.rows if row.candidate_id == cid), 1, 1, "交通行业", NOW, "某政策")
            for cid in ids
        }

    async def by_ids(_session: Any, ids: list[Any]) -> list[Any]:
        return [c for c in state.candidates.values() if c.id in ids]

    async def rows_to_apply(_session: Any, cid: Any, current: str) -> list[Any]:
        return [row for row in state.rows if row.candidate_id == cid and row.scenario_state not in (current, "重复")]

    async def get_for_update(_session: Any, cid: Any) -> Any:
        return next((c for c in state.candidates.values() if c.id == cid), None)

    async def record(_session: Any, **kwargs: Any) -> None:
        state.events.append(kwargs)

    monkeypatch.setattr(internal_clients, "codebook", state.codebook)
    for name, fake in {
        "ensure": ensure,
        "taken_relation_keys": taken,
        "stats": stats,
        "by_ids": by_ids,
        "rows_to_apply": rows_to_apply,
        "get_for_update": get_for_update,
    }.items():
        monkeypatch.setattr(repo, name, fake)
    monkeypatch.setattr(scenario_decisions, "enqueue_event", record)
    return state


def test_candidate_key_keeps_the_path_up_to_the_new_level_only() -> None:
    assert domain.candidate_key(domain.KIND_NEW, AIR, ("智慧航空", "智慧机场工程建设管理", "施工进度管理"), 2) == (
        "新|智慧航空>智慧机场工程建设管理"
    )
    assert domain.candidate_path(domain.KIND_NEW, ("中医药数智化", "国际交流", ""), 1) == ("中医药数智化", "", "")
    assert domain.candidate_key(domain.KIND_ASSOCIATION, AIR, TARGET, 0) == (
        "关联|交通行业/交通运输、仓储和邮政业/航空|智慧交通工程建设>交通工程建设信息化"
    )


async def test_classify_sorts_rows_by_what_the_codebook_says(world: SimpleNamespace) -> None:
    exists = _row(AIR, ("智慧航空", "智慧空侧", "行李自动化"))
    airport = _row(AIR, ("智慧航空", "智慧机场工程建设管理", "施工进度管理"))
    airport2 = _row(AIR, ("智慧航空", "智慧机场工程建设管理", ""), policy_uid="p2")
    tcm1 = _row(HEALTH, ("中医药数智化", "中医药国际交流合作平台", ""))
    tcm2 = _row(("重要客户服务二部", "", ""), ("中医药数智化", "中医药科研数智化平台", ""), policy_uid="p3")
    coded = _row(AIR, ("智慧航空", "智慧航站楼", ""), industry_scenario_code="0101060017246200", is_new_scenario="否")
    rows = [exists, airport, airport2, tcm1, tcm2, coded]
    world.rows = rows
    touched = await scenario_engine.classify_rows(Session(), rows, NOW)  # type: ignore[arg-type]

    # AI 说新增、码表里其实有：改成已有、回填编码、备注写明，关联主键换成编码形式
    assert (exists.scenario_state, exists.is_new_scenario, exists.industry_scenario_code) == (
        "码表已有",
        "否",
        "01010600172461199000",
    )
    assert scenario_engine.AUTO_EXISTS_NOTE in exists.remark and exists.relation_key == "p101010600172461199000TO_B"
    # 带编码的行不再去码表问
    assert coded.scenario_state == "码表已有"
    # 第二级是新的：带三级的、不带三级的归到同一个候选
    airport_key = "新|智慧航空>智慧机场工程建设管理"
    assert airport.candidate_id == airport2.candidate_id == world.candidates[airport_key].id
    assert (airport.scenario_state, airport.new_scenario_level) == ("待审", "二级")
    # 新的一级场景不分行业：两个行业提的是同一个候选
    assert tcm1.candidate_id == tcm2.candidate_id and tcm2.scenario_state == "待审"
    assert world.candidates["新|中医药数智化"].level_label == "一级"
    assert len(touched) == 2
    # 系统改的行只加版本号，不动更新时间（AI 靠它判断有没有人改过）
    assert all(row.version == 2 and row.updated_at == NOW for row in rows)


async def test_bad_industry_rows_do_not_become_candidates(world: SimpleNamespace) -> None:
    row = _row(("新行业", "", ""), ("中医药数智化", "", ""))
    await scenario_engine.classify_rows(Session(), [row], NOW)  # type: ignore[arg-type]
    assert (row.scenario_state, row.candidate_id) == ("行业不在码表", None) and not world.candidates


async def test_new_rows_follow_an_existing_merge_decision(world: SimpleNamespace) -> None:
    key = "新|智慧航空>智慧机场工程建设管理"
    world.candidates[key] = _candidate(
        key=key,
        kind=domain.KIND_NEW,
        new_level=2,
        level_label="二级",
        scenario_l1="智慧航空",
        scenario_l2="智慧机场工程建设管理",
        status=domain.STATUS_MERGED,
        target_l1=TARGET[0],
        target_l2=TARGET[1],
        decided_by_name="张三",
    )
    row = _row(AIR, ("智慧航空", "智慧机场工程建设管理", "施工进度管理"))
    world.rows = [row]
    await scenario_engine.classify_rows(Session(), [row], NOW)  # type: ignore[arg-type]
    # 说法记成了别名：以后 AI 再写，直接改成合并到的场景、回填它的编码
    assert (row.scenario_l1_name, row.scenario_l2_name, row.scenario_l3_name) == (*TARGET[:2], "")
    assert (row.scenario_state, row.industry_scenario_code) == ("已合并", "01010600300400000000")
    assert row.scenario_synced_at == NOW


async def test_adopt_renames_the_new_level_and_is_safe_to_repeat(world: SimpleNamespace) -> None:
    rows = [
        _row(AIR, ("智慧航空", "智慧机场工程建设管理", "施工进度管理")),
        _row(AIR, ("智慧航空", "智慧机场工程建设管理", ""), policy_uid="p2"),
    ]
    world.rows = rows
    await scenario_engine.classify_rows(Session(), rows, NOW)  # type: ignore[arg-type]
    candidate = world.candidates["新|智慧航空>智慧机场工程建设管理"]
    await scenario_decisions.adopt(Session(), ACTOR, candidate.id, version=1, name="智慧机场建设管理")  # type: ignore[arg-type]
    assert candidate.status == "已采纳" and candidate.decided_by_name == "张三"
    # 只换新的那一级，下级的三级场景留着
    assert [(row.scenario_l2_name, row.scenario_l3_name, row.scenario_state) for row in rows] == [
        ("智慧机场建设管理", "施工进度管理", "已采纳"),
        ("智慧机场建设管理", "", "已采纳"),
    ]
    assert all(row.industry_scenario_code.startswith("01010600") for row in rows)
    assert world.events[-1]["event_type"] == "policy.scenario_candidate.adopted"
    synced = len(world.codebook.synced)
    assert await scenario_engine.apply_decision(Session(), candidate, None, NOW) == []  # type: ignore[arg-type]
    assert len(world.codebook.synced) == synced  # 处理过的行不再动，也不再写码表


async def test_a_merged_row_that_duplicates_another_row_of_the_same_policy_is_marked(world: SimpleNamespace) -> None:
    row = _row(AIR, ("智慧航空", "智慧机场工程建设管理", ""))
    world.rows = [row]
    await scenario_engine.classify_rows(Session(), [row], NOW)  # type: ignore[arg-type]
    old_key = row.relation_key
    world.taken = {"p101010600300400000000TO_B"}  # 这条政策已有一行就是合并目标、机会类型相同
    candidate = world.candidates["新|智慧航空>智慧机场工程建设管理"]
    await scenario_decisions.merge(Session(), ACTOR, candidate.id, version=1, target=list(TARGET[:2]))  # type: ignore[arg-type]
    assert (row.scenario_state, row.relation_key) == ("重复", old_key)


async def test_merge_works_when_candidate_has_no_rows(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """新增候选没待套用行时也能验证码表目标存在并完成合并。"""

    empty_candidate = _candidate(
        key="新|另一新场景",
        kind="新",
        new_level=1,
        scenario_l1="另一新场景",
        scenario_l2="",
        scenario_l3="",
        industry_l1="",
        industry_l2="",
        industry_l3="",
    )
    world.candidates[empty_candidate.key] = empty_candidate
    original = world.codebook

    async def with_context(method: str, path: str, **kwargs: Any) -> list[dict[str, Any]]:
        if path.endswith("/context"):
            return [{"key": "target", "industries": ["交通行业"]}]
        return await original(method, path, **kwargs)

    monkeypatch.setattr(internal_clients, "codebook", with_context)
    await scenario_decisions.merge(Session(), ACTOR, empty_candidate.id, version=1, target=list(TARGET[:2]))  # type: ignore[arg-type]
    assert empty_candidate.status == "已合并"


async def test_merge_only_into_existing_scenarios(world: SimpleNamespace) -> None:
    row = _row(AIR, ("智慧航空", "智慧机场工程建设管理", ""))
    world.rows = [row]
    await scenario_engine.classify_rows(Session(), [row], NOW)  # type: ignore[arg-type]
    candidate = world.candidates["新|智慧航空>智慧机场工程建设管理"]
    with pytest.raises(ApiError, match="码表里没有这个场景"):
        await scenario_decisions.merge(Session(), ACTOR, candidate.id, version=1, target=["智慧航空", "另一个新说法"])  # type: ignore[arg-type]
    assert candidate.status == "待审"


async def test_reject_keeps_rows_and_only_rejected_can_reopen(world: SimpleNamespace) -> None:
    row = _row(AIR, ("智慧航空", "智慧机场工程建设管理", ""))
    world.rows = [row]
    await scenario_engine.classify_rows(Session(), [row], NOW)  # type: ignore[arg-type]
    candidate = world.candidates["新|智慧航空>智慧机场工程建设管理"]
    with pytest.raises(ApiError, match="驳回原因"):
        await scenario_decisions.reject(Session(), ACTOR, candidate.id, version=1, reason="随便", note="")  # type: ignore[arg-type]
    await scenario_decisions.reject(Session(), ACTOR, candidate.id, version=1, reason="说法不对", note="")  # type: ignore[arg-type]
    assert (candidate.status, row.scenario_state, row.scenario_l2_name) == ("已驳回", "已驳回", "智慧机场工程建设管理")
    with pytest.raises(ApiError, match="已经已驳回"):
        await scenario_decisions.adopt(Session(), ACTOR, candidate.id, version=2, name="")  # type: ignore[arg-type]
    await scenario_decisions.reopen(Session(), ACTOR, candidate.id, version=2)  # type: ignore[arg-type]
    assert (candidate.status, candidate.decided_by_name, row.scenario_state) == ("待审", "", "待审")
    with pytest.raises(ApiError, match="只有已驳回"):
        await scenario_decisions.reopen(Session(), ACTOR, candidate.id, version=3)  # type: ignore[arg-type]


async def test_new_candidates_cache_the_most_similar_existing_scenario(world: SimpleNamespace) -> None:
    row = _row(AIR, ("智慧航空", "智慧机场工程建设管理", ""))
    world.rows = [row]
    touched = await scenario_engine.classify_rows(Session(), [row], NOW)  # type: ignore[arg-type]
    await scenario_engine.settle(Session(), touched)  # type: ignore[arg-type]
    candidate = world.candidates["新|智慧航空>智慧机场工程建设管理"]
    assert (candidate.similar_name, candidate.similar_level, candidate.row_count) == (
        "智慧交通工程建设 > 交通工程建设信息化",
        "高",
        1,
    )


async def test_changing_one_row_is_a_human_edit_and_reclassifies_it(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.policy.repositories import interpretations as interpretations_repo

    row = _row(AIR, ("智慧航空", "智慧机场工程建设管理", ""))
    other = _row(AIR, ("智慧航空", "另一个", ""))
    world.rows = [row, other]
    await scenario_engine.classify_rows(Session(), [row], NOW)  # type: ignore[arg-type]
    old_candidate = row.candidate_id

    async def get_for_update(_session: Any, row_id: Any) -> Any:
        return next(item for item in world.rows if item.id == row_id)

    async def by_key(_session: Any, key: str) -> Any:
        return next((item for item in world.rows if item.relation_key == key), None)

    monkeypatch.setattr(interpretations_repo, "get_for_update", get_for_update)
    monkeypatch.setattr(interpretations_repo, "get_by_relation_key", by_key)
    names = dict(zip(SCENARIO_NAME_FIELDS, (*AIR, "智慧航空", "另一个", ""), strict=True))
    with pytest.raises(ApiError, match="同一场景"):
        await scenario_decisions.change_row_scenario(Session(), ACTOR, row.id, version=row.version, names=names)  # type: ignore[arg-type]
    names = dict(zip(SCENARIO_NAME_FIELDS, (*AIR, "智慧航空", "智慧空侧", "行李自动化"), strict=True))
    out = await scenario_decisions.change_row_scenario(Session(), ACTOR, row.id, version=row.version, names=names)  # type: ignore[arg-type]
    assert (out["scenario_state"], out["industry_scenario_code"], out["updated_by_name"]) == (
        "码表已有",
        "01010600172461199000",
        "张三",
    )
    assert row.candidate_id is None and old_candidate is not None
    assert world.events[-1]["event_type"] == "policy.interpretation.scenario_changed"


def _merging_fakes(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.policy.application import scenario_merging

    async def rows_of(_session: Any, cid: Any) -> list[Any]:
        return [row for row in world.rows if row.candidate_id == cid]

    async def others(_session: Any, exclude: Any) -> list[Any]:
        return [c for c in world.candidates.values() if c.id != exclude and c.status == "待审"]

    async def get(_session: Any, cid: Any) -> Any:
        return next((c for c in world.candidates.values() if c.id == cid), None)

    async def with_prefix(_session: Any, _path: Any) -> list[Any]:
        return []

    async def renamed(_session: Any, path: Any, new_name: str) -> int:
        world.renamed = (path, new_name)
        return 3

    async def no(_session: Any, _key: str) -> bool:
        return False

    for name, fake in {
        "rows_of": rows_of,
        "pending_others": others,
        "get": get,
        "candidates_with_prefix": with_prefix,
        "codeless_rows_with_prefix": with_prefix,
        "rename_rows": renamed,
        "key_taken": no,
    }.items():
        monkeypatch.setattr(repo, name, fake)
    monkeypatch.setattr(scenario_merging, "enqueue_event", world_record(world))


def world_record(world: SimpleNamespace) -> Any:
    async def record(_session: Any, **kwargs: Any) -> None:
        world.events.append(kwargs)

    return record


async def test_two_pending_scenarios_merge_into_one_and_the_alias_follows(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.policy.application import scenario_merging

    _merging_fakes(world, monkeypatch)
    main = _row(AIR, ("智慧航空", "智慧机场工程建设管理", ""))
    alias = _row(AIR, ("智慧航空", "机场建设数字化管理", "施工进度管理"), policy_uid="p2")
    world.rows = [main, alias]
    await scenario_engine.classify_rows(Session(), [main, alias], NOW)  # type: ignore[arg-type]
    target = world.candidates["新|智慧航空>智慧机场工程建设管理"]
    peer = world.candidates["新|智慧航空>机场建设数字化管理"]
    found = await scenario_merging.peers(Session(), target.id)  # type: ignore[arg-type]
    assert [item["name"] for item in found] == []  # 字面不像：只列名称相近的
    await scenario_merging.absorb(Session(), ACTOR, target.id, version=1, peer_id=peer.id, peer_version=1)  # type: ignore[arg-type]
    # 被并入的说法换成目标的说法，下级保留，行搬过来
    assert (alias.scenario_l2_name, alias.scenario_l3_name, alias.candidate_id) == (
        "智慧机场工程建设管理",
        "施工进度管理",
        target.id,
    )
    assert (peer.status, peer.merged_into) == ("已合并", target.id)
    # 以后 AI 再写被并入的说法：顺着归到目标场景
    later = _row(AIR, ("智慧航空", "机场建设数字化管理", ""), policy_uid="p3")
    world.rows.append(later)
    await scenario_engine.classify_rows(Session(), [later], NOW)  # type: ignore[arg-type]
    assert (later.candidate_id, later.scenario_l2_name, later.scenario_state) == (
        target.id,
        "智慧机场工程建设管理",
        "待审",
    )


async def test_absorb_refuses_scenarios_of_different_levels(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.policy.application import scenario_merging

    _merging_fakes(world, monkeypatch)
    rows = [_row(AIR, ("智慧航空", "智慧机场工程建设管理", "")), _row(HEALTH, ("中医药数智化", "", ""))]
    world.rows = rows
    await scenario_engine.classify_rows(Session(), rows, NOW)  # type: ignore[arg-type]
    first, second = world.candidates["新|智慧航空>智慧机场工程建设管理"], world.candidates["新|中医药数智化"]
    with pytest.raises(ApiError, match="级别不同"):
        await scenario_merging.absorb(Session(), ACTOR, first.id, version=1, peer_id=second.id, peer_version=1)  # type: ignore[arg-type]


async def test_merge_can_rename_the_existing_scenario_to_the_new_wording(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _merging_fakes(world, monkeypatch)
    calls: list[dict[str, Any]] = []
    original = world.codebook

    async def codebook(method: str, path: str, **kwargs: Any) -> Any:
        if path.endswith("/rename"):
            calls.append(kwargs["json"])
            CODEBOOK[(ROAD, ("智慧交通工程建设", "智慧机场工程建设管理", ""))] = "300400000000"
            return {"rows": 3}
        return await original(method, path, **kwargs)

    monkeypatch.setattr(internal_clients, "codebook", codebook)
    row = _row(AIR, ("智慧航空", "智慧机场工程建设管理", ""))
    world.rows = [row]
    await scenario_engine.classify_rows(Session(), [row], NOW)  # type: ignore[arg-type]
    candidate = world.candidates["新|智慧航空>智慧机场工程建设管理"]
    try:
        await scenario_decisions.merge(
            Session(),
            ACTOR,
            candidate.id,
            version=1,
            target=list(TARGET[:2]),
            rename=True,  # type: ignore[arg-type]
        )
    finally:
        CODEBOOK.pop((ROAD, ("智慧交通工程建设", "智慧机场工程建设管理", "")), None)
    assert calls[0]["path"] == list(TARGET[:2]) and calls[0]["new_name"] == "智慧机场工程建设管理"
    assert world.renamed == (TARGET[:2], "智慧机场工程建设管理")
    assert (candidate.target_l2, row.scenario_l1_name, row.scenario_l2_name, row.scenario_state) == (
        "智慧机场工程建设管理",
        "智慧交通工程建设",
        "智慧机场工程建设管理",
        "已合并",
    )


async def test_batch_reject_skips_ones_already_decided(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.policy.application import scenario_batch

    _merging_fakes(world, monkeypatch)
    rows = [_row(AIR, ("智慧航空", "智慧机场工程建设管理", "")), _row(HEALTH, ("中医药数智化", "", ""))]
    world.rows = rows
    await scenario_engine.classify_rows(Session(), rows, NOW)  # type: ignore[arg-type]
    first, second = world.candidates["新|智慧航空>智慧机场工程建设管理"], world.candidates["新|中医药数智化"]
    second.status = "已采纳"

    class Nested(Session):
        def begin_nested(self) -> Any:
            return self

        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    out = await scenario_batch.batch_reject(
        Nested(),
        ACTOR,
        [(first.id, 1), (second.id, 1)],
        reason="说法不对",
        note="",  # type: ignore[arg-type]
    )
    assert out["done"] == 1 and out["skipped"][0]["name"] == "中医药数智化" and "已采纳" in out["skipped"][0]["reason"]
    assert first.status == "已驳回"


async def test_batch_adopt_writes_each_into_the_codebook_and_skips_decided_ones(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.policy.application import scenario_batch

    _merging_fakes(world, monkeypatch)
    rows = [_row(AIR, ("智慧航空", "智慧机场工程建设管理", "")), _row(HEALTH, ("中医药数智化", "", ""))]
    world.rows = rows
    await scenario_engine.classify_rows(Session(), rows, NOW)  # type: ignore[arg-type]
    first, second = world.candidates["新|智慧航空>智慧机场工程建设管理"], world.candidates["新|中医药数智化"]
    second.status = "已驳回"

    class Nested(Session):
        def begin_nested(self) -> Any:
            return self

        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    out = await scenario_batch.batch_adopt(Nested(), ACTOR, [(first.id, 1), (second.id, 1)])  # type: ignore[arg-type]
    assert out["done"] == 1 and out["skipped"][0]["name"] == "中医药数智化"
    # 批量采纳不改名：沿用 AI 写的说法
    assert (first.status, first.adopted_name) == ("已采纳", "")
    assert rows[0].scenario_state == "已采纳" and rows[0].industry_scenario_code.startswith("01010600")


def test_source_rows_can_be_narrowed_to_one_industry() -> None:
    """来源政策抽屉「按行业看」：三级行业都对上才算，空的那级也要是空的。"""

    from sqlalchemy.dialects import postgresql

    query = repo._rows_query(uuid.uuid4(), None, ("医卫行业", "卫生", ""))
    sql = str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "industry_l1 = '医卫行业'" in sql and "industry_l2 = '卫生'" in sql and "industry_l3 = ''" in sql
    assert "industry_l1" not in str(repo._rows_query(uuid.uuid4(), None).whereclause)


def test_match_filter_puts_each_scenario_in_exactly_one_bucket() -> None:
    """列表「码表里像它的」：AI 说该合并的单独一类，其余按名称相似分，不会一个场景落两类。"""

    from sqlalchemy.dialects import postgresql

    def sql(value: str) -> str:
        _, condition = repo._conditions({"match": [value]})
        return str(condition.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    assert sql(domain.MATCH_AI) == "policy_scenario_candidates.ai_verdict IN ('同一个场景', '归到已有场景下')"
    for value in (domain.MATCH_HIGH, domain.MATCH_MEDIUM, domain.MATCH_NONE):
        assert "ai_verdict NOT IN ('同一个场景', '归到已有场景下')" in sql(value)
    assert "similar_level NOT IN ('高', '中')" in sql(domain.MATCH_NONE)
    with pytest.raises(KeyError):
        repo._conditions({"match": ["随便写的"]})
