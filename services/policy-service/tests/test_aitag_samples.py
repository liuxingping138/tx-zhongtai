"""从数据库取测试数据的查询：不加行锁、筛选走索引（精确比对、关键词按字面）、限时、限总字数，市场机会和定时任务同口径。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.aitag.application import samples
from app.aitag.repositories import tagging as repo
from app.common import policy_source

NOW = datetime(2026, 11, 1, tzinfo=UTC)


class CapturingSession:
    """记下执行过的语句，按 PostgreSQL 方言编译成 SQL 文本给断言用。"""

    def __init__(self) -> None:
        self.sql: list[str] = []
        self.params: list[dict[str, Any]] = []

    def _keep(self, statement: Any) -> None:
        compiled = statement.compile(dialect=postgresql.dialect())
        self.sql.append(str(compiled))
        self.params.append(dict(compiled.params))

    async def scalars(self, statement: Any) -> list[Any]:
        self._keep(statement)
        return []

    async def execute(self, statement: Any) -> None:
        self.sql.append(str(statement))


async def test_sample_filters_compare_exactly_and_keywords_literally() -> None:
    session = CapturingSession()
    await repo.recent_tags(
        session,  # type: ignore[arg-type]
        interpreted=True,
        limit=50,
        province=" 广东省 ",
        keyword="100%_政\\务",
        industry_l1=" 党政行业 ",
    )
    sql, params = session.sql[0], set(session.params[0].values())
    # 省份、一级行业精确比对才走得上各自的 B 树索引；包含匹配要整表扫
    assert "policy_base_tags.province_name = %(province_name_1)s" in sql
    assert "policy_interpretations.industry_l1 = %(industry_l1_1)s" in sql
    assert {"广东省", "党政行业"} <= params
    # 关键词里的 % _ \ 按字面找
    assert "policy_base_tags.policy_name ILIKE %(policy_name_1)s ESCAPE" in sql
    assert "%100\\%\\_政\\\\务%" in params
    assert "FOR UPDATE" not in sql and "ORDER BY policy_base_tags.interpreted_at DESC" in sql


async def test_blank_filters_are_ignored_and_industry_only_applies_to_interpreted_policies() -> None:
    session = CapturingSession()
    await repo.recent_tags(session, interpreted=False, limit=5, province=" ", keyword="", industry_l1="党政行业")  # type: ignore[arg-type]
    sql = session.sql[0]
    assert (
        "province_name" not in sql.split("WHERE", 1)[1] and "ILIKE" not in sql and "policy_interpretations" not in sql
    )


async def test_sample_reads_take_no_row_locks_and_are_time_limited() -> None:
    session = CapturingSession()
    await repo.interpretations_by_source_ids(session, ["c1"])  # type: ignore[arg-type]
    await repo.ai_interpretations(session, ["c1"])  # type: ignore[arg-type]
    await repo.limit_sample_queries(session)  # type: ignore[arg-type]
    readonly, locking, timeout = session.sql
    assert "FOR UPDATE" not in readonly and "FOR UPDATE" in locking  # 打标写回用加锁的那个
    assert timeout == "SET LOCAL statement_timeout = '15s'"
    assert await repo.interpretations_by_source_ids(session, []) == {}  # type: ignore[arg-type]


def test_page_day_read_filters_provinces_with_bound_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    executed: list[tuple[str, tuple[Any, ...]]] = []

    class Cursor:
        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, sql: str, params: Any) -> None:
            executed.append((sql, tuple(params)))

        def fetchall(self) -> list[dict[str, Any]]:
            return [{"content_id": "c1"}] if len(executed) == 1 else [{"content_id": "c1", "content": "正文"}]

    class Connection(Cursor):
        def cursor(self) -> Cursor:
            return Cursor()

    monkeypatch.setattr(policy_source, "_connect_for_page", Connection)
    day = date(2026, 10, 18)
    rows, contents = policy_source.read_day_for_page(day, 20, ["广东省", "北京市"])
    sql, params = executed[0]
    assert "prov_name IN (%s, %s)" in sql and params == (day, "", "广东省", "北京市", 20)
    assert rows == [{"content_id": "c1"}] and contents == {"c1": "正文"}
    executed.clear()
    policy_source.read_day_for_page(day, 20)
    assert "prov_name IN" not in executed[0][0] and executed[0][1] == (day, "", 20)


def _tag(source_id: str) -> Any:
    return SimpleNamespace(
        source_content_id=source_id, policy_name=f"{source_id} 方案", province_name="北京市", city_name="",
        issued_at="", issuing_dept="", policy_level="",
    )  # fmt: skip


def _row(source_id: str, industry: str, scene: str, *, status: str = "待验证", edited: bool = False) -> Any:
    return SimpleNamespace(
        source_content_id=source_id, industry_l1=industry, scenario_l1_name=scene, data_status=status,
        tagged_at=NOW, updated_at=NOW + timedelta(minutes=1) if edited else NOW,
    )  # fmt: skip


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(tags=[], rows={}, asked=[], read=[], timeouts=0)

    async def task(*_: Any) -> Any:
        return SimpleNamespace(content_max_chars=0)

    async def recent(_session: Any, **kwargs: Any) -> list[Any]:
        state.asked.append(kwargs)
        return state.tags[: kwargs["limit"]]

    async def grouped(_session: Any, ids: list[str]) -> dict[str, list[Any]]:
        return {key: value for key, value in state.rows.items() if key in ids}

    async def timeout(_session: Any) -> None:
        state.timeouts += 1

    def contents(ids: list[str]) -> dict[str, str]:
        state.read.append(ids)
        return dict.fromkeys(ids, "正文")

    async def locked(*_: Any) -> Any:
        raise AssertionError("取测试数据不能用加锁的查询")

    monkeypatch.setattr(samples.repo, "task", task)
    monkeypatch.setattr(samples.repo, "recent_tags", recent)
    monkeypatch.setattr(samples.repo, "interpretations_by_source_ids", grouped)
    monkeypatch.setattr(samples.repo, "ai_interpretations", locked)
    monkeypatch.setattr(samples.repo, "limit_sample_queries", timeout)
    monkeypatch.setattr(samples.source, "read_contents_for_page", contents)
    return state


def _pairs(out: dict[str, Any]) -> list[tuple[str, str, str]]:
    rows = [dict(zip(out["headers"], row, strict=True)) for row in out["rows"]]
    return [(row["源ID"], row["一级行业"], row["一级场景"]) for row in rows]


async def test_opportunity_samples_use_the_rows_the_scheduled_task_would_ask(world: SimpleNamespace) -> None:
    world.tags = [_tag("c1"), _tag("c2"), _tag("c3")]
    world.rows = {
        # 有没人改过的 AI 行：只用这些，和定时任务一样（人工核对过的「城市大脑」不出现）
        "c1": [_row("c1", "党政行业", "数字政府"), _row("c1", "党政行业", "城市大脑", status="人工验证")],
        # 全被人改过：退到它所有的行，取测试数据不该因此拿不到
        "c2": [_row("c2", "教育行业", "智慧校园", edited=True)],
        # 没有能用的行业场景：跳过，不占条数
        "c3": [_row("c3", "", "数字政府")],
    }
    out = await samples.samples(None, "opportunity", None, 10, samples.SampleFilter(province="北京市"))  # type: ignore[arg-type]
    assert _pairs(out) == [("c1", "党政行业", "数字政府"), ("c2", "教育行业", "智慧校园")]
    # 多取了候选（至少 50 条政策），省份照传；正文只读用得上的两条
    assert world.asked[0]["limit"] == 50 and world.asked[0]["province"] == "北京市"
    assert world.read == [["c1", "c2"]] and world.timeouts == 1


async def test_opportunity_samples_stop_at_the_requested_groups_and_filter_industry_exactly(
    world: SimpleNamespace,
) -> None:
    world.tags = [_tag("c1"), _tag("c2"), _tag("c3")]
    world.rows = {
        "c1": [_row("c1", "党政行业", "数字政府"), _row("c1", "党政行业二部", "x"), _row("c1", "党政行业", "城市大脑")],
        "c2": [_row("c2", "党政行业", "一网通办")],
        "c3": [_row("c3", "党政行业", "车路云")],
    }
    flt = samples.SampleFilter(industry_l1=" 党政行业 ")
    out = await samples.samples(None, "opportunity", None, 3, flt)  # type: ignore[arg-type]
    assert _pairs(out) == [
        ("c1", "党政行业", "数字政府"),
        ("c1", "党政行业", "城市大脑"),
        ("c2", "党政行业", "一网通办"),
    ]
    assert world.read == [["c1", "c2"]] and world.asked[0]["industry_l1"] == " 党政行业 "
    assert "3 条" in out["note"] and out["file_name"].endswith("-3条.xlsx")


async def test_interpret_samples_ignore_the_industry_filter(world: SimpleNamespace) -> None:
    world.tags = [_tag("c1")]
    out = await samples.samples(None, "interpret", None, 5, samples.SampleFilter(industry_l1="党政行业"))  # type: ignore[arg-type]
    assert world.asked[0]["industry_l1"] is None and world.asked[0]["limit"] == 5 and len(out["rows"]) == 1


async def test_samples_are_cut_at_the_character_budget(world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(samples, "CHARS_BUDGET", 30)
    world.tags = [_tag("c1"), _tag("c2"), _tag("c3")]
    out = await samples.samples(None, "interpret", None, 3)  # type: ignore[arg-type]
    # 每行约 15 字：前两行装得下，第三行超了；至少留一行
    assert len(out["rows"]) == 2 and "只取了前 2 条" in out["note"] and out["file_name"].endswith("-2条.xlsx")
    monkeypatch.setattr(samples, "CHARS_BUDGET", 1)
    assert len((await samples.samples(None, "interpret", None, 3))["rows"]) == 1  # type: ignore[arg-type]
