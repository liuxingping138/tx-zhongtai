"""认证用例：登录校验、会话签发、刷新轮换与宽限、改密后重新签发。仓储和令牌签发用替身。"""

from __future__ import annotations

import uuid
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.clock import utcnow
from platform_common.errors import ApiError, UnauthenticatedError

from app.application import auth_service as module
from app.application.auth_service import AuthService, load_principal
from app.domain.enums import UserStatus
from app.domain.password import hash_password
from app.domain.tokens import hash_refresh_token

GOOD_LOGIN = "correct-horse-1"
SETTINGS = SimpleNamespace(refresh_token_ttl_seconds=3600, refresh_reuse_grace_seconds=30)


class _Session:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.flush = AsyncMock()
        self.commit = AsyncMock()

    def add(self, row: Any) -> None:
        if getattr(row, "id", None) is None and type(row).__name__ == "RefreshToken":
            row.id = len(self.added) + 100
        self.added.append(row)


def _user(**overrides: Any) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "username": "zhangsan",
        "display_name": "张三",
        "status": UserStatus.ACTIVE,
        "password_hash": hash_password(GOOD_LOGIN),
        "must_change_password": False,
        "version": 1,
    }
    return SimpleNamespace(**(base | overrides))


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(
        events=[], payloads=[], user=None, token=None, session=None, revoked_family=[], revoked_user=0
    )

    async def enqueue(_s: object, *, event_type: str, payload: dict[str, object]) -> None:
        state.events.append(event_type)
        state.payloads.append(payload)

    def session_with_user(_s: object, session_id: uuid.UUID, user_id: uuid.UUID) -> Any:
        # 和真实查询一样按会话、账号联表：会话不属于这个账号就查不到。
        row, user = state.session, state.user
        if row is None or user is None or row.id != session_id or user.id != user_id or row.user_id != user.id:
            return None
        return row, user

    monkeypatch.setattr(module.outbox_repo, "enqueue", enqueue)
    monkeypatch.setattr(module, "issue_access_token", lambda **_: "access-token")
    monkeypatch.setattr(module.user_repo, "get_user_by_username", AsyncMock(side_effect=lambda *_: state.user))
    monkeypatch.setattr(module.user_repo, "get_user_by_id", AsyncMock(side_effect=lambda *_: state.user))
    monkeypatch.setattr(
        module.session_repo, "get_refresh_token_for_update", AsyncMock(side_effect=lambda *_: state.token)
    )
    monkeypatch.setattr(module.session_repo, "get_session", AsyncMock(side_effect=lambda *_: state.session))
    monkeypatch.setattr(module.session_repo, "get_session_with_user", AsyncMock(side_effect=session_with_user))
    monkeypatch.setattr(
        module.session_repo,
        "revoke_family",
        AsyncMock(side_effect=lambda _s, fid, **_: state.revoked_family.append(fid)),
    )
    monkeypatch.setattr(module.session_repo, "revoke_user_sessions", AsyncMock(return_value=4))
    monkeypatch.setattr(module.session_repo, "revoke_session", AsyncMock())
    return state


def _service() -> AuthService:
    return AuthService(_Session(), SETTINGS)  # type: ignore[arg-type]


class TestAuthenticate:
    async def test_correct_password_returns_the_user(self, env: SimpleNamespace) -> None:
        env.user = _user()
        assert await _service().authenticate_password(" ZhangSan ", GOOD_LOGIN) is env.user

    @pytest.mark.parametrize("case", ["no-user", "wrong-password"])
    async def test_failures_share_one_message(self, env: SimpleNamespace, case: str) -> None:
        env.user = None if case == "no-user" else _user()
        with pytest.raises(UnauthenticatedError, match=module.UNIFIED_LOGIN_FAILURE):
            await _service().authenticate_password("zhangsan", "wrong-password-1")

    async def test_disabled_account_is_told_apart_only_after_the_password_is_right(self, env: SimpleNamespace) -> None:
        env.user = _user(status=UserStatus.DISABLED)
        with pytest.raises(UnauthenticatedError, match="账号不可用"):
            await _service().authenticate_password("zhangsan", GOOD_LOGIN)
        with pytest.raises(UnauthenticatedError, match=module.UNIFIED_LOGIN_FAILURE):
            await _service().authenticate_password("zhangsan", "wrong-password-1")

    async def test_weak_hash_is_upgraded_on_login(self, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
        env.user = _user()
        old_hash = env.user.password_hash
        monkeypatch.setattr(module, "needs_rehash", lambda _h: True)
        await _service().authenticate_password("zhangsan", GOOD_LOGIN)
        assert env.user.password_hash != old_hash


class TestIssue:
    async def test_login_issues_a_session_with_a_hashed_refresh_token(self, env: SimpleNamespace) -> None:
        service = _service()
        access, refresh, session_row = await service.login_success(
            _user(), request_id="r1", client_ip="10.0.0.1", user_agent="ua"
        )
        assert access == "access-token"
        stored = next(row for row in service.session.added if type(row).__name__ == "RefreshToken")  # type: ignore[attr-defined]
        assert stored.token_hash == hash_refresh_token(refresh) != refresh
        assert session_row.client_info == {"ip": "10.0.0.1", "user_agent": "ua"}
        assert env.events == ["auth.login.succeeded"]

    async def test_failure_is_recorded_with_the_normalised_username(self, env: SimpleNamespace) -> None:
        await _service().record_login_failure(
            username=" ZhangSan ", request_id=None, client_ip="1.1.1.1", user_agent="ua", reason="bad"
        )
        assert env.events == ["auth.login.failed"]
        assert env.payloads[0]["username"] == "zhangsan"
        assert "actor_id" not in env.payloads[0] and "actor_name" not in env.payloads[0]

    async def test_failure_of_a_real_account_is_tied_to_the_person(self, env: SimpleNamespace) -> None:
        """成功行记显示名，失败行也要记上这个人：按人筛登录日志才看得到把他锁住的那些失败。"""

        env.user = _user()
        await _service().record_login_failure(
            username="ZhangSan", request_id=None, client_ip="1.1.1.1", user_agent="ua", reason="locked_account"
        )
        payload = env.payloads[0]
        assert payload["actor_id"] == str(env.user.id)
        assert payload["actor_name"] == "张三"
        assert payload["username"] == "zhangsan"
        lookup = module.user_repo.get_user_by_username
        assert lookup.await_args.args[1] == "zhangsan"  # type: ignore[attr-defined]  # 替身上的调用记录


def _refresh_fixture(env: SimpleNamespace, **token: Any) -> str:
    now = utcnow()
    raw = "raw-refresh"
    env.user = _user()
    env.session = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=env.user.id,
        family_id=uuid.uuid4(),
        revoked_at=None,
        expires_at=now + timedelta(hours=1),
        last_seen_at=now,
    )
    base = {
        "id": 1,
        "session_id": env.session.id,
        "token_hash": hash_refresh_token(raw),
        "consumed_at": None,
        "replaced_by": None,
        "expires_at": now + timedelta(hours=1),
    }
    env.token = SimpleNamespace(**(base | token))
    return raw


class TestRefresh:
    async def test_normal_refresh_rotates_the_token(self, env: SimpleNamespace) -> None:
        raw = _refresh_fixture(env)
        service = _service()
        access, new_raw, session_row, user = await service.refresh(raw)
        assert access == "access-token" and new_raw and new_raw != raw
        assert env.token.consumed_at is not None and env.token.replaced_by is not None
        assert user is env.user and session_row is env.session

    async def test_unknown_token_is_rejected(self, env: SimpleNamespace) -> None:
        env.token = None
        with pytest.raises(UnauthenticatedError, match="无效"):
            await _service().refresh("nope")

    async def test_token_without_a_session_is_rejected(self, env: SimpleNamespace) -> None:
        raw = _refresh_fixture(env)
        env.session = None
        with pytest.raises(UnauthenticatedError, match="无效"):
            await _service().refresh(raw)

    async def test_reuse_inside_grace_returns_a_new_access_token_only(self, env: SimpleNamespace) -> None:
        raw = _refresh_fixture(env, consumed_at=utcnow() - timedelta(seconds=5), replaced_by=2)
        access, new_raw, *_ = await _service().refresh(raw)
        assert access == "access-token" and new_raw is None

    async def test_reuse_after_grace_revokes_the_family_and_commits_first(self, env: SimpleNamespace) -> None:
        raw = _refresh_fixture(env, consumed_at=utcnow() - timedelta(minutes=5), replaced_by=2)
        service = _service()
        with pytest.raises(UnauthenticatedError, match="已失效"):
            await service.refresh(raw)
        assert env.revoked_family == [env.session.family_id]
        assert env.events == ["auth.refresh.replayed"]
        service.session.commit.assert_awaited_once()  # type: ignore[attr-defined]

    async def test_expired_token_and_disabled_user_are_rejected(self, env: SimpleNamespace) -> None:
        raw = _refresh_fixture(env, expires_at=utcnow() - timedelta(seconds=1))
        with pytest.raises(UnauthenticatedError, match="已过期"):
            await _service().refresh(raw)
        raw = _refresh_fixture(env)
        env.user.status = UserStatus.DISABLED
        with pytest.raises(UnauthenticatedError, match="账号不可用"):
            await _service().refresh(raw)


class TestLogoutAndPassword:
    async def test_logout_revokes_one_session_and_logout_all_counts(self, env: SimpleNamespace) -> None:
        session_row = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
        service = _service()
        await service.logout(session_row)  # type: ignore[arg-type]
        assert await service.logout_all(_user()) == 4  # type: ignore[arg-type]
        assert env.events == ["auth.logout", "auth.logout_all"]

    async def test_change_password_rotates_everything(self, env: SimpleNamespace) -> None:
        user = _user(must_change_password=True)
        access, refresh, _ = await _service().change_password(user, GOOD_LOGIN, "brand-new-pass-9")  # type: ignore[arg-type]
        assert user.must_change_password is False and user.version == 2
        assert access and refresh
        assert env.events == ["auth.password.changed"]

    async def test_change_password_rules(self, env: SimpleNamespace) -> None:
        user = _user()
        # 原密码错回 422 不回 401：401 会让前端当成会话过期，先续期再重发。
        with pytest.raises(ApiError, match="原密码") as wrong:
            await _service().change_password(user, "wrong-password-1", "brand-new-pass-9")  # type: ignore[arg-type]
        assert wrong.value.http_status == 422
        with pytest.raises(ApiError):
            await _service().change_password(user, GOOD_LOGIN, "1")  # type: ignore[arg-type]
        with pytest.raises(ApiError, match="不能与原密码相同"):
            await _service().change_password(user, GOOD_LOGIN, GOOD_LOGIN)  # type: ignore[arg-type]


class TestActivity:
    """在线用户的「最近活跃」：带令牌的请求都算，但每台设备最多每分钟写一次库，写在独立短事务里。"""

    @pytest.fixture
    def db(self, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
        state = SimpleNamespace(opened=0, commit=AsyncMock(), touch=AsyncMock(return_value=True), fail=False)

        class _Db:
            async def __aenter__(self) -> Any:
                if state.fail:
                    raise OSError("db down")
                state.opened += 1
                return SimpleNamespace(commit=state.commit)

            async def __aexit__(self, *_: object) -> None:
                return None

        monkeypatch.setattr(module, "SideSessionLocal", _Db)
        monkeypatch.setattr(module.session_repo, "touch_last_seen", state.touch)
        return state

    async def test_recent_activity_is_not_written_again(self, db: SimpleNamespace) -> None:
        row = SimpleNamespace(id=uuid.uuid4(), last_seen_at=utcnow() - timedelta(seconds=30))
        await module.note_activity(row, every_seconds=60)  # type: ignore[arg-type]
        assert db.opened == 0

    async def test_stale_activity_is_written_in_its_own_transaction(self, db: SimpleNamespace) -> None:
        row = SimpleNamespace(id=uuid.uuid4(), last_seen_at=utcnow() - timedelta(minutes=10))
        await module.note_activity(row, every_seconds=60)  # type: ignore[arg-type]
        assert db.opened == 1
        db.commit.assert_awaited_once()
        kwargs = db.touch.await_args.kwargs
        assert kwargs["now"] - kwargs["stale_before"] == timedelta(seconds=60)
        assert db.touch.await_args.args[1] == row.id

    async def test_a_failed_write_does_not_fail_the_request(self, db: SimpleNamespace) -> None:
        db.fail = True
        row = SimpleNamespace(id=uuid.uuid4(), last_seen_at=utcnow() - timedelta(minutes=10))
        await module.note_activity(row, every_seconds=60)  # type: ignore[arg-type]


class TestPrincipal:
    async def test_active_user_with_a_usable_session(self, env: SimpleNamespace) -> None:
        _refresh_fixture(env)
        user, session_row = await load_principal(object(), env.user.id, env.session.id)  # type: ignore[arg-type]
        assert user is env.user and session_row is env.session

    async def test_every_inconsistency_is_unauthenticated(self, env: SimpleNamespace) -> None:
        _refresh_fixture(env)
        env.session.revoked_at = utcnow()
        with pytest.raises(UnauthenticatedError):
            await load_principal(object(), env.user.id, env.session.id)  # type: ignore[arg-type]
        _refresh_fixture(env)
        env.session.user_id = uuid.uuid4()
        with pytest.raises(UnauthenticatedError):
            await load_principal(object(), env.user.id, env.session.id)  # type: ignore[arg-type]
        _refresh_fixture(env)
        env.user.status = UserStatus.DISABLED
        with pytest.raises(UnauthenticatedError, match="账号不可用"):
            await load_principal(object(), env.user.id, env.session.id)  # type: ignore[arg-type]
        env.user = None
        with pytest.raises(UnauthenticatedError):
            await load_principal(object(), uuid.uuid4(), uuid.uuid4())  # type: ignore[arg-type]
