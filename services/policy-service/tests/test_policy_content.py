"""政策正文按需从源库取：手工行说明没有正文，源库连不上说清楚，取到的是打标同一口径的文字。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pymysql
import pytest
from platform_common.errors import DependencyUnavailableError, NotFoundError

from app.common import policy_source as source
from app.policy.application import base_tags, interpretations, policy_content

HTML = "<html><body><div class='nav'>首页</div><p>第一段。</p><p>第二段。</p></body></html>"


async def test_content_is_the_same_text_the_model_sees(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        source,
        "read_page",
        lambda content_id: (
            {
                "content_id": content_id,
                "name": 'document.write("x".length>9?"":"真标题")',
                "original_link": "https://a.gov.cn/1",
                "introduced_date": "2026-10-01",
            },
            HTML,
        ),
    )
    data = await policy_content.policy_content("c1")
    assert data == {
        "title": "真标题",
        "text": "第一段。\n第二段。",
        "source_url": "https://a.gov.cn/1",
        "issued_at": "2026-10-01",
        "chars": 9,
    }


async def test_rows_without_a_source_id_and_missing_sources_are_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(NotFoundError, match="没有正文"):
        await policy_content.policy_content(None)
    monkeypatch.setattr(source, "read_page", lambda _id: (None, None))
    with pytest.raises(NotFoundError, match="已经找不到"):
        await policy_content.policy_content("gone")
    monkeypatch.setattr(source, "read_page", lambda _id: ({"content_id": "c1"}, None))
    with pytest.raises(NotFoundError, match="已经找不到"):
        await policy_content.policy_content("c1")

    def down(_id: str) -> Any:
        raise OSError("mysql down")

    monkeypatch.setattr(source, "read_page", down)
    with pytest.raises(DependencyUnavailableError, match="源库暂时连不上"):
        await policy_content.policy_content("c1")

    monkeypatch.setattr(
        source,
        "read_page",
        lambda _id: ({"content_id": "c1", "name": "恶意链接", "original_link": "javascript:alert(1)"}, "<p>ok</p>"),
    )
    assert (await policy_content.policy_content("c1"))["source_url"] == ""


class _Cursor:
    def __init__(self, replies: list[Any]) -> None:
        self.replies = replies
        self.queries: list[tuple[str, list[str]]] = []

    def execute(self, sql: str, params: list[str]) -> None:
        self.queries.append((sql, params))

    def fetchone(self) -> Any:
        return self.replies.pop(0)

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _Cursor:
        return self._cursor

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_page_reads_one_policy_and_its_html_over_a_single_short_lived_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[dict[str, Any]] = []
    cursor = _Cursor([{"content_id": "c1", "name": "标题"}, {"content_id": "c1", "content": "<p>正文</p>"}])

    def connect(database: str, **timeouts: Any) -> _Connection:
        opened.append(timeouts)
        return _Connection(cursor)

    monkeypatch.setattr(source, "mysql_connect", connect)
    assert source.read_page("c1") == ({"content_id": "c1", "name": "标题"}, "<p>正文</p>")
    # 人在页面上等：几秒连不上、二十秒读不回就放弃，不沿用同步任务的 30 秒连接、20 分钟读取。
    assert opened == [{"connect_timeout": 5, "read_timeout": 20}]
    assert [params for _sql, params in cursor.queries] == [["c1"], ["c1"]]
    assert "csys_policy_info_content" in cursor.queries[1][0]

    # 源库里没有这条政策：不再去读正文表。
    cursor = _Cursor([None])
    assert source.read_page("gone") == (None, None)
    assert len(cursor.queries) == 1


def test_page_read_does_not_retry_when_the_source_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def connect(database: str, **_timeouts: Any) -> _Connection:
        calls.append(database)
        raise pymysql.err.OperationalError(2003, "can't connect")

    monkeypatch.setattr(source, "mysql_connect", connect)
    with pytest.raises(pymysql.err.OperationalError):
        source.read_page("c1")
    assert len(calls) == 1


async def test_both_tables_look_up_the_row_then_its_source_id(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str | None] = []

    async def fake_content(source_content_id: str | None) -> dict[str, Any]:
        asked.append(source_content_id)
        return {"text": "正文"}

    async def get_by_id(_session: Any, item_id: uuid.UUID) -> Any:
        return SimpleNamespace(source_content_id=str(item_id)[:4]) if str(item_id).startswith("1") else None

    monkeypatch.setattr(base_tags, "policy_content", fake_content)
    monkeypatch.setattr(interpretations, "policy_content", fake_content)
    monkeypatch.setattr(base_tags.repo, "get_by_id", get_by_id)
    monkeypatch.setattr(interpretations.repo, "get_by_id", get_by_id)
    found = uuid.UUID("11111111-1111-1111-1111-111111111111")
    assert await base_tags.base_tag_content(object(), found) == {"text": "正文"}  # type: ignore[arg-type]
    assert await interpretations.interpretation_content(object(), found) == {"text": "正文"}  # type: ignore[arg-type]
    assert asked == ["1111", "1111"]
    with pytest.raises(NotFoundError):
        await base_tags.base_tag_content(object(), uuid.UUID("22222222-2222-2222-2222-222222222222"))  # type: ignore[arg-type]


async def test_policy_contents_by_source_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_contents(content_ids: list[str]) -> dict[str, str]:
        return {cid: f"<p>{cid}正文内容</p>" for cid in content_ids}

    monkeypatch.setattr(source, "read_contents_for_page", fake_contents)
    contents = await policy_content.policy_contents_by_source_ids(["c1", "c2", ""])
    assert contents == {"c1": "c1正文内容", "c2": "c2正文内容"}


async def test_policy_contents_by_source_ids_raises_503_on_source_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_content_ids: list[str]) -> dict[str, str]:
        raise OSError("mysql down")

    monkeypatch.setattr(source, "read_contents_for_page", broken)
    with pytest.raises(DependencyUnavailableError):
        await policy_content.policy_contents_by_source_ids(["c1"])


async def test_attach_policy_contents(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    def fake_contents(content_ids: list[str]) -> dict[str, str]:
        events.append("read_source")
        return {cid: f"{cid}正文" for cid in content_ids}

    monkeypatch.setattr(source, "read_contents_for_page", fake_contents)

    item1 = SimpleNamespace(source_content_id="s1", policy_title="政策1")
    item2 = SimpleNamespace(source_content_id=None, policy_title="政策2")
    item3 = SimpleNamespace(source_content_id=None, policy_title="")

    class _FakeResult:
        def all(self) -> list[tuple[str, str]]:
            return [("政策2", "s2")]

    class _FakeSession:
        async def execute(self, _stmt: Any) -> Any:
            return _FakeResult()

        async def commit(self) -> None:
            events.append("commit")

    rows: list[dict[str, Any]] = [{}, {}, {}]
    await policy_content.attach_policy_contents(_FakeSession(), [item1, item2, item3], rows)  # type: ignore[arg-type]

    assert rows[0]["policy_content"] == "s1正文"
    assert rows[1]["policy_content"] == "s2正文"
    assert rows[2]["policy_content"] == ""
    # 先提交放掉 PostgreSQL 事务，再去源库读：读几百批期间事务开着会撞空闲事务超时
    assert events[0] == "commit" and "read_source" in events


async def test_attach_policy_contents_without_source_ids_never_touches_the_source() -> None:
    rows: list[dict[str, Any]] = [{}]
    item = SimpleNamespace(source_content_id=None, policy_title="")
    await policy_content.attach_policy_contents(object(), [item], rows)  # type: ignore[arg-type]
    assert rows == [{"policy_content": ""}]
