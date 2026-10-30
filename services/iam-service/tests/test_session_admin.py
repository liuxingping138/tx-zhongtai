"""在线用户与登录锁定：锁定剩余时间、解锁、按设备下线。"""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.clock import utcnow
from platform_common.errors import ApiError, NotFoundError
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
    base = {"id": uuid.uuid4(), "username": "zhangsan", "display_name": "张三", "status": UserStatus.ACTIVE}
    return SimpleNamespace(**(base | overrides))


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
    await session_admin.revoke_one(object(), _user(), env.row.id, current_session_id=uuid.uuid4())  # type: ignore[arg-type]
    assert env.row.revoked_at is not None
    assert env.events == ["iam.session.revoked"]


async def test_revoking_an_already_ended_session_says_so(env: SimpleNamespace) -> None:
    env.user = _user()
    env.row = SimpleNamespace(
        id=uuid.uuid4(), user_id=env.user.id, revoked_at=utcnow(), expires_at=utcnow() + timedelta(hours=1)
    )
    with pytest.raises(NotFoundError, match="已经下线"):
        await session_admin.revoke_one(object(), _user(), env.row.id, current_session_id=uuid.uuid4())  # type: ignore[arg-type]


async def test_the_device_in_use_cannot_be_revoked_here(env: SimpleNamespace) -> None:
    """正在用的这台下线就等于退出登录，误点会把自己踢出去；要退出用「退出登录」。"""

    env.user = _user()
    env.row = SimpleNamespace(
        id=uuid.uuid4(), user_id=env.user.id, revoked_at=None, expires_at=utcnow() + timedelta(hours=1)
    )
    with pytest.raises(ApiError, match="正在用的这台设备"):
        await session_admin.revoke_one(object(), env.user, env.row.id, current_session_id=env.row.id)  # type: ignore[arg-type]
    assert env.row.revoked_at is None
    assert env.events == []


def _session_row(user_id: uuid.UUID, *, seen_minutes_ago: int) -> SimpleNamespace:
    now = utcnow()
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        client_info={"ip": "10.0.0.1", "user_agent": "ua"},
        created_at=now - timedelta(days=1),
        last_seen_at=now - timedelta(minutes=seen_minutes_ago),
    )


async def test_online_means_active_in_the_window_and_rows_say_what_i_can_do(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """有效登录全列出来，30 分钟内有操作的才标在线；我正在用的这台、超级管理员的设备都不给下线。"""

    me, colleague, boss = _user(), _user(username="lisi"), _user(username="admin")
    mine = _session_row(me.id, seen_minutes_ago=0)
    idle = _session_row(colleague.id, seen_minutes_ago=31)
    busy = _session_row(boss.id, seen_minutes_ago=5)
    rows = [(mine, me), (busy, boss), (idle, colleague)]
    monkeypatch.setattr(session_admin.session_repo, "list_active_sessions", AsyncMock(return_value=rows))
    manageable = AsyncMock(return_value={me.id, colleague.id})
    monkeypatch.setattr(session_admin, "manageable_ids", manageable)

    result = await session_admin.list_online(
        object(),  # type: ignore[arg-type]
        me,  # type: ignore[arg-type]
        current_session_id=mine.id,
        online_window_seconds=30 * 60,
    )

    items = {item["id"]: item for item in result["items"]}  # type: ignore[attr-defined]
    assert result["online_window_seconds"] == 1800
    assert (items[str(mine.id)]["online"], items[str(mine.id)]["current"], items[str(mine.id)]["can_manage"]) == (
        True,
        True,
        False,
    )
    assert (items[str(idle.id)]["online"], items[str(idle.id)]["can_manage"]) == (False, True)
    assert (items[str(busy.id)]["online"], items[str(busy.id)]["can_manage"]) == (True, False)
    assert sorted(manageable.await_args.args[2]) == sorted({me.id, colleague.id, boss.id})
