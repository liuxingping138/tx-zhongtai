"""筛选项预览与服务端搜索。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from platform_common import options as mod
from platform_common.options import PREVIEW_LIMIT, preview_options, search_options


class _Column:
    """够用的假列：只记录被调用过哪些条件。"""

    def __init__(self) -> None:
        self.like: str | None = None

    def is_not(self, _other: object) -> _Column:
        return self

    def __ne__(self, _other: object) -> _Column:  # type: ignore[override]
        return self

    def ilike(self, pattern: str, escape: str | None = None) -> _Column:
        self.like = pattern
        return self


def _patch_distinct(monkeypatch: pytest.MonkeyPatch, values: list[str]) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    async def fake(_session: object, _column: object, limit: int) -> list[str]:
        seen["limit"] = limit
        return values[:limit]

    monkeypatch.setattr(mod, "_distinct", fake)
    return seen


def test_preview_marks_truncated_when_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch_distinct(monkeypatch, [f"值{i}" for i in range(PREVIEW_LIMIT + 50)])
    result = asyncio.run(preview_options(object(), {"site_name": _Column()}))  # type: ignore[arg-type]

    assert result["site_name"]["truncated"] is True
    assert len(result["site_name"]["items"]) == PREVIEW_LIMIT
    # 多取一条用来判断截断，不额外跑 count
    assert seen["limit"] == PREVIEW_LIMIT + 1


def test_preview_not_truncated_when_within_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_distinct(monkeypatch, ["北京市", "上海市", "广东省"])
    result = asyncio.run(preview_options(object(), {"province_name": _Column()}))  # type: ignore[arg-type]

    assert result["province_name"]["truncated"] is False
    assert result["province_name"]["items"] == ["北京市", "上海市", "广东省"]


def test_preview_exactly_at_limit_is_not_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_distinct(monkeypatch, [f"值{i}" for i in range(PREVIEW_LIMIT)])
    result = asyncio.run(preview_options(object(), {"tag": _Column()}))  # type: ignore[arg-type]

    assert result["tag"]["truncated"] is False


def test_search_rejects_unknown_field() -> None:
    """未知字段必须报错，不能静默返回空列表——否则下拉一直空着很难排查。"""

    with pytest.raises(KeyError):
        asyncio.run(search_options(object(), {"tag": _Column()}, field="zz_nope", keyword="x"))  # type: ignore[arg-type]


def test_search_builds_contains_pattern(monkeypatch: pytest.MonkeyPatch) -> None:
    column = _Column()
    captured: dict[str, Any] = {}

    class _Result:
        def scalars(self) -> list[str]:
            return ["北京市人民政府"]

    class _Session:
        async def execute(self, stmt: object) -> _Result:
            captured["stmt"] = stmt
            return _Result()

    monkeypatch.setattr(mod, "select", lambda _col: _Stmt())
    values = asyncio.run(search_options(_Session(), {"site_name": column}, field="site_name", keyword=" 北京 "))
    assert values == ["北京市人民政府"]
    assert column.like == "%北京%"  # 关键词两端空白要去掉


class _Stmt:
    def where(self, *_args: object) -> _Stmt:
        return self

    def distinct(self) -> _Stmt:
        return self

    def order_by(self, *_args: object) -> _Stmt:
        return self

    def limit(self, *_args: object) -> _Stmt:
        return self


def test_blank_keyword_does_not_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    """关键词为空时只按上限取前若干候选，不拼 ilike。"""

    column = _Column()

    class _Result:
        def scalars(self) -> list[str]:
            return ["甲", "乙"]

    class _Session:
        async def execute(self, _stmt: object) -> _Result:
            return _Result()

    monkeypatch.setattr(mod, "select", lambda _col: _Stmt())
    values = asyncio.run(search_options(_Session(), {"tag": column}, field="tag", keyword="   "))
    assert values == ["甲", "乙"]
    assert column.like is None
