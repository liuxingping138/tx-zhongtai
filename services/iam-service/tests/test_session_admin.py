"""在线用户与登录锁定：锁定剩余时间、解锁、按设备下线。"""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.clock import utcnow
from platform_common.errors import NotFoundError
from redis.exceptions import RedisError

from app.application import session_admin
from app.core.config import get_settings
from app.core.rate_limit import LoginLockouts, user_lock_key
from app.domain.enums import UserStatus


class _Redis:
    def __init__(self, counts: dict[str, int], ttls: dict[str, int], fail: bool = False) -> None:
        self.counts = counts
        self.ttls = ttls
        self.fail = fail
        self.deleted: list[str] = []

    async def mget(self, keys: list[str]) -> list[Any]:
        if self.fail:
            raise RedisError("down")
        return [self.counts.get(key) for key in keys]

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -2)

    async def delete(self, key: str) -> int:
        self.deleted.append(key)
        return 1 if self.counts.pop(key, None) is not None else 0


def _lockouts(redis: _Redis) -> LoginLockouts:
    return LoginLockouts(redis, get_settings())  # type: ignore[arg-type]


async def test_only_accounts_over_the_limit_count_as_locked() -> None:
    redis = _Redis(
        counts={user_lock_key("zhangsan"): 5, user_lock_key("lisi"): 2},
        ttls={user_lock_key("zhangsan"): 240, user_lock_key("lisi"): 280},
    )
    items: list[dict[str, object]] = [{"username": "ZhangSan"}, {"username": "lisi"}, {"username": "wangwu"}]
    await session_admin.with_lockouts(items, _lockouts(redis))
    assert [item["locked_seconds"] for item in items] == [240, 0, 0]


async def test_redis_down_does_not_break_the_user_list() -> None:
    items: list[dict[str, object]] = [{"username": "zhangsan"}]
    await session_admin.with_lockouts(items, _lockouts(_Redis({}, {}, fail=True)))
    assert items[0]["locked_seconds"] == 0


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(user=None, row=None, events=[])
    monkeypatch.setattr(session_admin.user_repo, "get_user_by_id", AsyncMock(side_effect=lambda *_: state.user))
    monkeypatch.setattr(session_admin.session_repo, "get_session", AsyncMock(side_effect=lambda *_: state.row))
    monkeypatch.setattr(session_admin, "assert_can_manage_target", AsyncMock())

    async def _enqueue(_session: object, *, event_type: str, payload: dict[str, object]) -> None:
        state.events.append(event_type)

    monkeypatch.setattr(session_admin.outbox_repo, "enqueue", _enqueue)
    return state


def _user(**overrides: Any) -> SimpleNamespace:
    return SimpleNamespace(**({"id": uuid.uuid4(), "username": "zhangsan", "status": UserStatus.ACTIVE} | overrides))


async def test_unlock_clears_the_counter_and_is_audited(env: SimpleNamespace) -> None:
    env.user = _user()
    redis = _Redis(counts={user_lock_key("zhangsan"): 5}, ttls={})
    assert await session_admin.unlock(object(), _user(), env.user.id, _lockouts(redis)) is True  # type: ignore[arg-type]
    assert redis.deleted == [user_lock_key("zhangsan")]
    assert env.events == ["iam.user.unlocked"]


async def test_unlock_of_a_deleted_user_is_not_found(env: SimpleNamespace) -> None:
    env.user = _user(status=UserStatus.DELETED)
    with pytest.raises(NotFoundError):
        await session_admin.unlock(object(), _user(), env.user.id, _lockouts(_Redis({}, {})))  # type: ignore[arg-type]


async def test_revoke_one_only_touches_that_session(env: SimpleNamespace) -> None:
    env.user = _user()
    env.row = SimpleNamespace(
        id=uuid.uuid4(), user_id=env.user.id, revoked_at=None, expires_at=utcnow() + timedelta(hours=1)
    )
    await session_admin.revoke_one(object(), _user(), env.row.id)  # type: ignore[arg-type]
    assert env.row.revoked_at is not None
    assert env.events == ["iam.session.revoked"]


async def test_revoking_an_already_ended_session_says_so(env: SimpleNamespace) -> None:
    env.user = _user()
    env.row = SimpleNamespace(
        id=uuid.uuid4(), user_id=env.user.id, revoked_at=utcnow(), expires_at=utcnow() + timedelta(hours=1)
    )
    with pytest.raises(NotFoundError, match="已经下线"):
        await session_admin.revoke_one(object(), _user(), env.row.id)  # type: ignore[arg-type]
