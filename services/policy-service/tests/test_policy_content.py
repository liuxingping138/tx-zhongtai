"""政策正文按需从源库取：手工行说明没有正文，源库连不上说清楚，取到的是打标同一口径的文字。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from platform_common.errors import DependencyUnavailableError, NotFoundError

from app.aitag.repositories import source
from app.policy.application import base_tags, interpretations, policy_content

HTML = "<html><body><div class='nav'>首页</div><p>第一段。</p><p>第二段。</p></body></html>"


async def test_content_is_the_same_text_the_model_sees(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        source,
        "read_by_ids",
        lambda ids: [
            {
                "content_id": ids[0],
                "name": 'document.write("x".length>9?"":"真标题")',
                "original_link": "https://a.gov.cn/1",
                "introduced_date": "2026-10-01",
            }
        ],
    )
    monkeypatch.setattr(source, "read_contents", lambda ids: {ids[0]: HTML})
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
    monkeypatch.setattr(source, "read_by_ids", lambda _ids: [])
    monkeypatch.setattr(source, "read_contents", lambda _ids: {})
    with pytest.raises(NotFoundError, match="已经找不到"):
        await policy_content.policy_content("gone")

    def down(_ids: list[str]) -> Any:
        raise OSError("mysql down")

    monkeypatch.setattr(source, "read_by_ids", down)
    with pytest.raises(DependencyUnavailableError, match="源库暂时连不上"):
        await policy_content.policy_content("c1")


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
