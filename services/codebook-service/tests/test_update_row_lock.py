"""更新路径必须锁行的回归测试。

version 比对是「先读后写」，SQLAlchemy 发出的 UPDATE 不带版本条件。更新路径若用
不加锁的 get_by_id，两个并发请求会读到同一个 version、双双通过校验，后提交的静默
覆盖前一个，两边都收到 200。详见 policy-service 的同名用例。
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from platform_common.errors import VersionConflictError

from app.application import area_codes, policy_types, scenarios
from app.repositories import area_codes as area_codes_repo
from app.repositories import policy_types as policy_types_repo
from app.repositories import scenarios as scenarios_repo

UPDATES = [
    (policy_types, "update_policy_type"),
    (scenarios, "update_scenario"),
    (area_codes, "update_area_code"),
]

REPOS = [policy_types_repo, scenarios_repo, area_codes_repo]


class _FakeActor:
    id = "u1"
    name = "测试"


class _RecordingSession:
    """只记录 session.get 的调用参数，不连数据库。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def get(self, _model: object, _item_id: object, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return object()


@pytest.mark.parametrize("repo", REPOS, ids=lambda item: item.__name__.rsplit(".", 1)[-1])
def test_get_for_update_requests_a_row_lock(repo: Any) -> None:
    session = _RecordingSession()
    asyncio.run(repo.get_for_update(session, uuid.uuid4()))
    assert session.calls == [{"with_for_update": True}]


@pytest.mark.parametrize("repo", REPOS, ids=lambda item: item.__name__.rsplit(".", 1)[-1])
def test_get_by_id_stays_lock_free_for_reads(repo: Any) -> None:
    """详情查询不该锁行，否则读请求会互相阻塞。"""

    session = _RecordingSession()
    asyncio.run(repo.get_by_id(session, uuid.uuid4()))
    assert session.calls == [{}]


@pytest.mark.parametrize(("module", "update_fn"), UPDATES, ids=[item[1] for item in UPDATES])
def test_update_reads_through_the_row_lock(monkeypatch: pytest.MonkeyPatch, module: Any, update_fn: str) -> None:
    """更新必须走 get_for_update，并且仍然按 version 拦下过期提交。"""

    class _Row:
        version = 7

    def fail_unlocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("更新路径用了不加锁的 get_by_id，并发更新会静默丢失")

    async def fake_locked(_session: object, _item_id: object) -> _Row:
        return _Row()

    monkeypatch.setattr(module.repo, "get_by_id", fail_unlocked)
    monkeypatch.setattr(module.repo, "get_for_update", fake_locked)

    with pytest.raises(VersionConflictError):
        asyncio.run(getattr(module, update_fn)(object(), _FakeActor(), uuid.uuid4(), {"version": 1}))
