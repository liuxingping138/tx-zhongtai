"""第 2、3 步用内存替身跑一遍：解读写行、查编码、失败写备注、费用到上限不记进度、市场机会回填。

真实库上的行为在集成测试里。
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.aitag.application import interpreting, pipeline
from app.aitag.application.pipeline import Spend
from app.aitag.repositories import source
from app.aitag.repositories import tagging as repo
from app.common import internal_clients
from app.policy.domain.models import Interpretation


class Session:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, item: Any) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _tag(source_id: str) -> Any:
    return SimpleNamespace(
        id=uuid.uuid4(),
        source_content_id=source_id,
        policy_name=f"{source_id} 方案",
        province_name="北京市",
        city_name="北京市",
        issued_at="2026-09-30",
        issuing_dept="市数据局",
        policy_level="地市级",
        remark="",
        interpreted_at=None,
        opportunity_at=None,
        version=1,
    )


def _answer(scene_l1: str, scene_l2: str, new: str) -> dict[str, str]:
    return {"一级行业": "党政行业", "一级场景": scene_l1, "二级场景": scene_l2, "机会类型": "TO_G", "是否新增场景": new}


ANSWERS = {
    "政策解读": {
        "c1": [
            _answer("数字政府", "一网统管", "否"),
            _answer("数字政府", "鸿蒙政务", "否"),
            _answer("城市大脑", "", "是"),
        ],
    },
    "市场机会": {"c1": [{"行业": "党政行业", "场景": "数字政府", "市场机会": "机会A"}]},
}


class FakeAi:
    """c2 回答失败，c3 没轮到（费用到上限），其余按 ANSWERS。"""

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def _row(self, row: dict[str, Any], stage: str) -> dict[str, Any]:
        source_id = row["源ID"]
        if source_id == "c2":
            return {"source_id": "c2", "items": [], "error": "限流"}
        if source_id == "c3":
            return {"source_id": "c3", "items": [], "error": "未执行（任务停止或中断）"}
        if stage == "市场机会":
            scene = row.get("一级场景", "")
            items = (
                [{"行业": row.get("一级行业", ""), "场景": scene, "市场机会": f"机会-{scene}"}]
                if scene == "数字政府"
                else []
            )
            return {"source_id": source_id, "items": items, "error": ""}
        return {"source_id": source_id, "items": ANSWERS[stage][source_id], "error": ""}

    async def __call__(self, method: str, path: str, **kwargs: Any) -> Any:
        if method == "POST":
            self.created.append(kwargs["json"])
            return {"id": f"{len(self.created):032d}"}
        if path.endswith("/results"):
            body = self.created[-1]
            stage = next(name for name in ANSWERS if name in body["caller_name"])
            return {"items": [self._row(row, stage) for row in body["rows"]]}
        return {"status": "done", "inference_cost": "0.2", "search_cost": "0", "error_message": "达到本批费用上限"}


async def fake_codebook(_method: str, _path: str, **kwargs: Any) -> list[dict[str, str]]:
    """只有「数字政府/一网统管」在码表里。"""

    return [
        {**item, "industry_scenario_code": "0102", "industry_code": "01", "scenario_code": "02"}
        if item["scenario_l2_name"] == "一网统管"
        else {**item, "industry_scenario_code": "", "industry_code": "", "scenario_code": ""}
        for item in kwargs["json"]["items"]
    ]


def _stub_scenario_engine(state: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    """新增场景归集在别处测：这里只记下删掉的旧行要重算哪些候选、写完有没有接着比对。"""

    async def recount(_session: Any, ids: Any) -> None:
        state.recounted.append(set(ids))

    async def sweep() -> int:
        state.swept += 1
        return 0

    monkeypatch.setattr(interpreting.scenario_engine, "recount", recount)
    monkeypatch.setattr(interpreting.scenario_engine, "classify_backlog", sweep)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    session = Session()
    run = SimpleNamespace(
        cost=Decimal(0), interpret_rows=0, interpret_failed=0, opportunity_rows=0, opportunity_failed=0
    )
    ai = FakeAi()
    state = SimpleNamespace(
        session=session, run=run, created=ai.created, events=[], deleted=[], tags=[], rows={}, recounted=[], swept=0
    )

    async def backlog(*_: Any) -> list[Any]:
        return state.tags

    async def by_ids(_session: Any, ids: list[Any]) -> dict[Any, Any]:
        return {tag.id: tag for tag in state.tags if tag.id in ids}

    async def grouped(*_: Any) -> dict[str, list[Any]]:
        return state.rows

    async def none(*_: Any) -> set[str]:
        return set()

    async def delete(_session: Any, rows: list[Any]) -> None:
        state.deleted.extend(rows)

    async def get_run(*_: Any) -> Any:
        return run

    async def record(_session: Any, **kwargs: Any) -> None:
        state.events.append(kwargs)

    for module in (interpreting, pipeline):
        monkeypatch.setattr(module, "SessionLocal", lambda: session)
    monkeypatch.setattr(pipeline, "POLL_SECONDS", 0)
    monkeypatch.setattr(internal_clients, "ai", ai)
    monkeypatch.setattr(internal_clients, "codebook", fake_codebook)
    monkeypatch.setattr(source, "read_contents", lambda ids: dict.fromkeys(ids, "正文"))
    monkeypatch.setattr(repo, "interpret_backlog", backlog)
    monkeypatch.setattr(repo, "opportunity_backlog", backlog)
    monkeypatch.setattr(repo, "base_tags_by_ids", by_ids)
    monkeypatch.setattr(repo, "ai_interpretations", grouped)
    monkeypatch.setattr(repo, "taken_relation_keys", none)
    monkeypatch.setattr(repo, "delete_rows", delete)
    monkeypatch.setattr(repo, "get_run", get_run)
    monkeypatch.setattr(interpreting, "enqueue_event", record)
    _stub_scenario_engine(state, monkeypatch)
    return state


CONFIG = SimpleNamespace(batch_size=10, content_max_chars=1000, prompt_id="p" * 32)


async def test_interpretation_writes_rows_codes_and_remarks(world: SimpleNamespace) -> None:
    world.tags = [_tag("c1"), _tag("c2"), _tag("c3")]
    spend = Spend(limit=Decimal(10), before=Decimal(1))
    note = await interpreting.interpret_step(uuid.uuid4(), CONFIG, spend)  # type: ignore[arg-type]
    rows = [item for item in world.session.added if isinstance(item, Interpretation)]
    assert [(row.scenario_l2_name, row.industry_scenario_code, row.is_new_scenario) for row in rows] == [
        ("一网统管", "0102", "否"),
        ("鸿蒙政务", "", "否"),
        ("", "", "是"),
    ]
    assert "码表里没对上" in rows[1].remark and rows[0].remark == ""
    c1, c2, c3 = world.tags
    assert c1.interpreted_at and c2.interpreted_at and c3.interpreted_at is None  # c3 没轮到，下批再做
    assert "AI 解读失败：限流" in c2.remark
    assert (world.run.interpret_rows, world.run.interpret_failed, spend.run) == (3, 1, Decimal("0.2"))
    assert "1 条下批接着解读" in note and world.created[0]["cost_limit"] == "9"


async def test_reinterpretation_replaces_only_untouched_ai_rows(world: SimpleNamespace) -> None:
    now = pipeline.datetime.now(pipeline.UTC)
    candidate = uuid.uuid4()
    untouched = SimpleNamespace(
        data_status="待验证", tagged_at=now, updated_at=now, source_content_id="c1", candidate_id=candidate
    )
    edited = SimpleNamespace(
        data_status="待验证",
        tagged_at=now,
        updated_at=now + timedelta(minutes=1),
        source_content_id="c1",
        candidate_id=None,
    )
    verified = SimpleNamespace(
        data_status="人工验证", tagged_at=now, updated_at=now, source_content_id="c1", candidate_id=None
    )
    world.tags, world.rows = [_tag("c1")], {"c1": [untouched, edited, verified]}
    await interpreting.interpret_step(uuid.uuid4(), CONFIG, Spend(limit=Decimal(10), before=Decimal(0)))  # type: ignore[arg-type]
    assert world.deleted == [untouched]
    # 删掉的旧行归属的新增场景候选少了几行，要重算；写完新行接着和码表比对
    assert world.recounted == [{candidate}] and world.swept == 1


async def test_opportunities_fill_matching_untouched_rows(world: SimpleNamespace) -> None:
    now = pipeline.datetime.now(pipeline.UTC)

    def row(scene: str, status: str = "待验证") -> Any:
        return SimpleNamespace(
            industry_l1="党政行业",
            scenario_l1_name=scene,
            data_status=status,
            tagged_at=now,
            updated_at=now,
            source_content_id="c1",
            market_opportunity="",
            version=1,
        )

    matched, other, verified = row("数字政府"), row("城市大脑"), row("数字政府", "人工验证")
    world.tags, world.rows = [_tag("c1")], {"c1": [matched, other, verified]}
    note = await interpreting.opportunity_step(uuid.uuid4(), CONFIG, Spend(limit=Decimal(10), before=Decimal(0)))  # type: ignore[arg-type]
    assert (matched.market_opportunity, other.market_opportunity, verified.market_opportunity) == (
        "机会-数字政府",
        "",
        "",
    )
    # 回填要加版本号：正开着这行编辑的人保存时会提示「被改过」，不会用空值把这次结果冲掉。
    assert (matched.version, other.version) == (2, 1)
    sent_rows = world.created[0]["rows"]
    assert [(r["一级行业"], r["一级场景"]) for r in sent_rows] == [("党政行业", "数字政府"), ("党政行业", "城市大脑")]
    assert sent_rows[0]["行业场景"] == "党政行业/数字政府"
    assert (
        world.tags[0].opportunity_at is not None
        and "回填 1 行" in note
        and "没有返回这一组的市场机会" in world.tags[0].remark
    )


async def test_policies_without_interpretation_rows_skip_the_model(world: SimpleNamespace) -> None:
    world.tags, world.rows = [_tag("c9")], {}
    note = await interpreting.opportunity_step(uuid.uuid4(), CONFIG, Spend(limit=Decimal(10), before=Decimal(0)))  # type: ignore[arg-type]
    assert note == "没有待补市场机会的政策" and world.created == []
    assert world.tags[0].opportunity_at is not None
    world.tags = []
    assert await interpreting.interpret_step(uuid.uuid4(), CONFIG, Spend(limit=Decimal(1), before=Decimal(0))) == (  # type: ignore[arg-type]
        "没有待解读的政策"
    )


def _scene_row(industry: str, scene: str, source_id: str = "c1", opportunity: str = "") -> Any:
    now = pipeline.datetime.now(pipeline.UTC)
    return SimpleNamespace(
        industry_l1=industry,
        scenario_l1_name=scene,
        data_status="待验证",
        tagged_at=now,
        updated_at=now,
        source_content_id=source_id,
        market_opportunity=opportunity,
        version=1,
    )


def _scripted_ask(monkeypatch: pytest.MonkeyPatch, answers: dict[str, dict[str, Any]]) -> list[list[str]]:
    """按一级场景给回答；没写的场景当作没轮到（费用到上限）。返回每批问了哪些场景。"""

    batches: list[list[str]] = []

    async def ask(*_: Any, rows: list[dict[str, str]], **__: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        batches.append([row["一级场景"] for row in rows])
        skipped = {"items": [], "error": "未执行（任务停止或中断）"}
        return {"error_message": "达到本批费用上限"}, [answers.get(row["一级场景"], skipped) for row in rows]

    monkeypatch.setattr(interpreting, "ask", ask)
    return batches


async def test_answered_groups_are_kept_when_the_policy_is_cut_off_and_only_open_groups_are_asked_again(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """费用到上限把一条政策从中间截断：答好的组当场写回，政策不记完成；下批只问还空着的组，已付费的不重问。"""

    done, broken, cut = (
        _scene_row("党政行业", "数字政府"),
        _scene_row("党政行业", "城市大脑"),
        _scene_row("党政行业", "一网通办"),
    )
    world.tags, world.rows = [_tag("c1")], {"c1": [done, broken, cut]}
    batches = _scripted_ask(
        monkeypatch,
        {"数字政府": {"items": [{"市场机会": "机会甲"}], "error": ""}, "城市大脑": {"items": [], "error": "限流"}},
    )
    spend = Spend(limit=Decimal(10), before=Decimal(0))
    note = await interpreting.opportunity_step(uuid.uuid4(), CONFIG, spend)  # type: ignore[arg-type]
    tag = world.tags[0]
    assert (done.market_opportunity, broken.market_opportunity, cut.market_opportunity) == ("机会甲", "", "")
    # 没问完：不记完成、不记失败（出错的组下批还会重问）
    assert tag.opportunity_at is None and tag.remark == "" and "1 条下批接着补" in note

    # 下一批：只问空着的两组，这次都答了（城市大脑仍然答不出），政策记完成，失败写进备注。
    others = [
        {"行业": "交通行业", "场景": "车路云", "市场机会": "x"},
        {"行业": "教育行业", "场景": "校园", "市场机会": "y"},
    ]
    answers: dict[str, dict[str, Any]] = {"城市大脑": {"items": others, "error": ""}}
    answers["一网通办"] = {"items": [{"市场机会": "机会丙"}], "error": ""}
    batches_next = _scripted_ask(monkeypatch, answers)
    await interpreting.opportunity_step(uuid.uuid4(), CONFIG, spend)  # type: ignore[arg-type]
    assert batches == [["数字政府", "城市大脑", "一网通办"]] and batches_next == [["城市大脑", "一网通办"]]
    assert (done.market_opportunity, cut.market_opportunity, done.version) == ("机会甲", "机会丙", 2)
    assert tag.opportunity_at is not None and "城市大脑：没有返回这一组的市场机会" in tag.remark


async def test_an_answer_whose_rows_were_edited_meanwhile_is_recorded_as_failed(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = _scene_row("党政行业", "数字政府")
    world.tags, world.rows = [_tag("c1")], {"c1": [row]}

    async def ask(*_: Any, rows: list[dict[str, str]], **__: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        row.updated_at = row.tagged_at + timedelta(minutes=1)  # 问的这段时间里有人改了这行
        return {}, [{"items": [{"市场机会": "机会"}], "error": ""}]

    monkeypatch.setattr(interpreting, "ask", ask)
    note = await interpreting.opportunity_step(uuid.uuid4(), CONFIG, Spend(limit=Decimal(10), before=Decimal(0)))  # type: ignore[arg-type]
    assert row.market_opportunity == "" and "回填 0 行，失败 1 条" in note
    assert "解读行已被人工修改或删除" in world.tags[0].remark


async def test_policies_with_nothing_left_to_ask_are_closed_without_the_model(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """组都补过了、行业场景是空的政策不去问模型，直接记完成。"""

    filled, blank = _scene_row("党政行业", "数字政府", "c1", "已有机会"), _scene_row("", "数字政府", "c2")
    world.tags, world.rows = [_tag("c1"), _tag("c2")], {"c1": [filled], "c2": [blank]}
    batches = _scripted_ask(monkeypatch, {})
    note = await interpreting.opportunity_step(uuid.uuid4(), CONFIG, Spend(limit=Decimal(10), before=Decimal(0)))  # type: ignore[arg-type]
    assert note == "没有待补市场机会的政策" and batches == []
    assert all(tag.opportunity_at is not None for tag in world.tags)


async def test_one_batch_asks_about_batch_size_times_groups_per_policy_without_splitting_a_policy(
    world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """上限按整条政策算：第一条组再多也整条问，到上限后后面的政策留到下批，不读它们的正文、不记完成。"""

    big = [f"场景{index}" for index in range(interpreting.GROUPS_PER_POLICY + 2)]
    world.tags = [_tag("c1"), _tag("c2"), _tag("c3")]
    world.rows = {
        "c1": [_scene_row("党政行业", scene) for scene in big],
        "c2": [_scene_row("教育行业", "智慧校园", "c2")],
        "c3": [_scene_row("交通行业", "车路云", "c3")],
    }
    answers = {scene: {"items": [{"市场机会": scene}], "error": ""} for scene in [*big, "智慧校园", "车路云"]}
    batches = _scripted_ask(monkeypatch, answers)
    read: list[list[str]] = []
    monkeypatch.setattr(source, "read_contents", lambda ids: read.append(ids) or dict.fromkeys(ids, "正文"))
    config = SimpleNamespace(batch_size=1, content_max_chars=1000, prompt_id="p" * 32)
    note = await interpreting.opportunity_step(uuid.uuid4(), config, Spend(limit=Decimal(10), before=Decimal(0)))  # type: ignore[arg-type]
    assert batches == [big] and read == [["c1"]]
    c1, c2, c3 = world.tags
    assert c1.opportunity_at is not None and c2.opportunity_at is None and c3.opportunity_at is None
    assert f"这批问到 {len(big)} 组已到上限，另外 2 条政策下批再问" in note

    # 下一批：c1 补完了，c2、c3 各一组，加起来没到上限，一起问
    config.batch_size = 2
    await interpreting.opportunity_step(uuid.uuid4(), config, Spend(limit=Decimal(10), before=Decimal(0)))  # type: ignore[arg-type]
    assert batches[-1] == ["智慧校园", "车路云"] and c2.opportunity_at and c3.opportunity_at
