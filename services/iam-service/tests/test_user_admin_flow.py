"""用户管理用例：建人、改人、重置密码、分配角色，以及「最后一个超级管理员」「受保护账号」两道保护。仓储用替身。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.errors import ApiError, NotFoundError, PermissionDeniedError, VersionConflictError
from sqlalchemy.exc import IntegrityError

from app.application import user_admin
from app.application.user_fields import NewUser, UserChanges
from app.domain.enums import UserStatus
from app.domain.filters import UserFilters

NOW = datetime(2026, 10, 1, tzinfo=UTC)
ACTOR = SimpleNamespace(id=uuid.uuid4())


def _user(**overrides: Any) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "username": "zhangsan",
        "display_name": "张三",
        "phone": "",
        "email": "",
        "status": UserStatus.ACTIVE,
        "must_change_password": True,
        "last_login_at": None,
        "last_login_ip": "",
        "version": 1,
        "created_at": NOW,
        "updated_at": NOW,
    }
    return SimpleNamespace(**(base | overrides))


class _Session:
    def __init__(self, flush_error: Exception | None = None) -> None:
        self.added: list[Any] = []
        self.flush = AsyncMock(side_effect=flush_error)

    def add(self, row: Any) -> None:
        self.added.append(row)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """把仓储换成替身，并记下发出的审计事件和被吊销的会话。"""

    state = SimpleNamespace(
        events=[], independent=[], user=_user(), roles=[], role_ids=[], superadmin_ids=set(), locked=[]
    )

    async def enqueue(_s: object, *, event_type: str, payload: dict[str, object]) -> None:
        state.events.append((event_type, payload))

    async def independent(*, event_type: str, payload: dict[str, object]) -> None:
        state.independent.append((event_type, payload))

    monkeypatch.setattr(user_admin.outbox_repo, "enqueue", enqueue)
    monkeypatch.setattr(user_admin, "enqueue_independent", independent)
    monkeypatch.setattr(user_admin.user_repo, "get_user_for_update", AsyncMock(side_effect=lambda *_: state.user))
    monkeypatch.setattr(user_admin.user_repo, "get_user_by_id", AsyncMock(side_effect=lambda *_: state.user))
    monkeypatch.setattr(
        user_admin.user_repo,
        "user_has_builtin_superadmin",
        AsyncMock(side_effect=lambda _s, uid: uid in state.superadmin_ids),
    )
    monkeypatch.setattr(
        user_admin.user_repo,
        "builtin_superadmin_ids",
        AsyncMock(side_effect=lambda _s, ids: {uid for uid in ids if uid in state.superadmin_ids}),
    )
    monkeypatch.setattr(user_admin.user_repo, "lock_superadmin_users", AsyncMock(side_effect=lambda *_: state.locked))
    monkeypatch.setattr(user_admin.user_repo, "replace_user_roles", AsyncMock())
    monkeypatch.setattr(user_admin.user_repo, "list_user_role_ids", AsyncMock(side_effect=lambda *_: state.role_ids))
    monkeypatch.setattr(user_admin.role_repo, "get_roles_by_ids", AsyncMock(side_effect=lambda *_: state.roles))
    monkeypatch.setattr(user_admin.session_repo, "revoke_user_sessions", AsyncMock(return_value=2))
    monkeypatch.setattr(user_admin.grant_repo, "count_by_users", AsyncMock(return_value={}))
    monkeypatch.setattr(user_admin.grant_repo, "list_for_user", AsyncMock(return_value=[]))
    return state


class TestCreateUser:
    async def test_without_password_a_temporary_one_is_generated_and_hashed(self, env: SimpleNamespace) -> None:
        session = _Session()
        payload, temporary = await user_admin.create_user(
            session, ACTOR, NewUser(username="LiSi", display_name=" 李四 ")
        )  # type: ignore[arg-type]

        row = session.added[0]
        assert (row.username, row.display_name, row.must_change_password) == ("lisi", "李四", True)
        assert temporary and row.password_hash != temporary
        assert payload["roles"] == [] and payload["role_ids"] == []
        assert env.events[0][0] == "iam.user.created"

    async def test_given_password_is_checked_against_the_policy(self, env: SimpleNamespace) -> None:
        with pytest.raises(ApiError):
            await user_admin.create_user(_Session(), ACTOR, NewUser(username="lisi", display_name="李四", password="1"))  # type: ignore[arg-type]

    async def test_precomputed_hash_skips_hashing_and_temporary_password(self, env: SimpleNamespace) -> None:
        session = _Session()
        _, temporary = await user_admin.create_user(
            session,
            ACTOR,
            NewUser(username="lisi", display_name="李四", password_hash="already-hashed"),  # type: ignore[arg-type]
        )
        assert temporary is None
        assert session.added[0].password_hash == "already-hashed"

    async def test_duplicate_username_is_a_conflict(self, env: SimpleNamespace) -> None:
        session = _Session(flush_error=IntegrityError("insert", {}, Exception("unique")))
        with pytest.raises(VersionConflictError, match="用户名已存在"):
            await user_admin.create_user(session, ACTOR, NewUser(username="lisi", display_name="李四"))  # type: ignore[arg-type]

    async def test_blank_display_name_is_rejected_before_anything_is_written(self, env: SimpleNamespace) -> None:
        session = _Session()
        with pytest.raises(ApiError, match="显示名"):
            await user_admin.create_user(session, ACTOR, NewUser(username="lisi", display_name="  "))  # type: ignore[arg-type]
        assert session.added == []

    async def test_roles_are_assigned_in_the_same_call(self, env: SimpleNamespace) -> None:
        role = SimpleNamespace(id=uuid.uuid4(), code="editor", name="编辑", status="active", is_builtin=False)
        env.roles = [role]
        payload, _ = await user_admin.create_user(
            _Session(),
            ACTOR,
            NewUser(username="lisi", display_name="李四", role_ids=[role.id]),  # type: ignore[arg-type]
        )
        assert payload["role_ids"] == [str(role.id)]
        assert [event for event, _ in env.events] == ["iam.user.created", "iam.user.roles_replaced"]


class TestUpdateUser:
    async def test_stale_version_is_rejected(self, env: SimpleNamespace) -> None:
        with pytest.raises(VersionConflictError):
            await user_admin.update_user(object(), ACTOR, env.user.id, UserChanges(version=9))  # type: ignore[arg-type]

    async def test_profile_fields_are_normalised_and_version_bumps(self, env: SimpleNamespace) -> None:
        payload = await user_admin.update_user(
            object(),
            ACTOR,
            env.user.id,  # type: ignore[arg-type]
            UserChanges(version=1, display_name=" 张小三 ", phone="138 2200 4411", email="a@b.com"),
        )
        assert (payload["display_name"], payload["phone"], payload["email"], payload["version"]) == (
            "张小三",
            "13822004411",
            "a@b.com",
            2,
        )
        assert env.events[0][0] == "iam.user.updated"

    async def test_empty_phone_clears_it(self, env: SimpleNamespace) -> None:
        env.user.phone = "13822004411"
        await user_admin.update_user(object(), ACTOR, env.user.id, UserChanges(version=1, phone=""))  # type: ignore[arg-type]
        assert env.user.phone == ""

    async def test_disabling_revokes_sessions(self, env: SimpleNamespace) -> None:
        await user_admin.update_user(object(), ACTOR, env.user.id, UserChanges(version=1, status="disabled"))  # type: ignore[arg-type]
        assert env.user.status == "disabled"
        user_admin.session_repo.revoke_user_sessions.assert_awaited_once()  # type: ignore[attr-defined]

    async def test_deleted_is_not_a_status_you_can_set_here(self, env: SimpleNamespace) -> None:
        with pytest.raises(ApiError, match="无效的用户状态"):
            await user_admin.update_user(object(), ACTOR, env.user.id, UserChanges(version=1, status="deleted"))  # type: ignore[arg-type]

    async def test_deleted_account_cannot_be_edited(self, env: SimpleNamespace) -> None:
        env.user.status = UserStatus.DELETED
        with pytest.raises(NotFoundError):
            await user_admin.update_user(object(), ACTOR, env.user.id, UserChanges(version=1))  # type: ignore[arg-type]


class TestProtections:
    async def test_only_a_superadmin_may_manage_a_superadmin(self, env: SimpleNamespace) -> None:
        env.superadmin_ids = {env.user.id}
        with pytest.raises(PermissionDeniedError, match="受保护"):
            await user_admin.reset_password(object(), ACTOR, env.user.id)  # type: ignore[arg-type]
        assert env.independent[0][0] == "iam.user.protect_denied"

    async def test_a_superadmin_may_manage_a_superadmin(self, env: SimpleNamespace) -> None:
        env.superadmin_ids = {env.user.id, ACTOR.id}
        assert await user_admin.reset_password(object(), ACTOR, env.user.id)  # type: ignore[arg-type]

    async def test_last_loginable_superadmin_cannot_be_disabled(self, env: SimpleNamespace) -> None:
        env.superadmin_ids = {ACTOR.id}
        env.locked = [env.user]
        with pytest.raises(PermissionDeniedError, match="最后一个"):
            await user_admin.update_user(object(), ACTOR, env.user.id, UserChanges(version=1, status="disabled"))  # type: ignore[arg-type]
        assert env.independent[-1][0] == "iam.superadmin.protect"

    async def test_another_superadmin_left_means_it_is_allowed(self, env: SimpleNamespace) -> None:
        env.superadmin_ids = {ACTOR.id}
        env.locked = [env.user, _user(status=UserStatus.ACTIVE)]
        await user_admin.update_user(object(), ACTOR, env.user.id, UserChanges(version=1, status="disabled"))  # type: ignore[arg-type]
        assert env.user.status == "disabled"


class TestResetAndRevoke:
    async def test_reset_password_forces_a_change_and_drops_sessions(self, env: SimpleNamespace) -> None:
        env.user.must_change_password = False
        temporary = await user_admin.reset_password(object(), ACTOR, env.user.id)  # type: ignore[arg-type]
        assert temporary and env.user.must_change_password is True
        assert env.user.password_hash != temporary
        assert env.events[0][0] == "iam.user.password_reset"

    async def test_revoke_sessions_reports_the_count(self, env: SimpleNamespace) -> None:
        assert await user_admin.revoke_sessions(object(), ACTOR, env.user.id) == 2  # type: ignore[arg-type]
        assert env.events[0][1]["revoked_count"] == 2


class TestRoleAssignment:
    async def test_unknown_role_is_rejected(self, env: SimpleNamespace) -> None:
        with pytest.raises(ApiError, match="未知角色"):
            await user_admin.replace_roles(object(), ACTOR, env.user.id, [uuid.uuid4()], version=1)  # type: ignore[arg-type]

    async def test_replace_requires_the_current_version(self, env: SimpleNamespace) -> None:
        with pytest.raises(VersionConflictError):
            await user_admin.replace_roles(object(), ACTOR, env.user.id, [], version=5)  # type: ignore[arg-type]

    async def test_removing_the_superadmin_role_goes_through_the_last_admin_guard(self, env: SimpleNamespace) -> None:
        env.superadmin_ids = {env.user.id, ACTOR.id}
        env.locked = [env.user]
        with pytest.raises(PermissionDeniedError, match="最后一个"):
            await user_admin.replace_roles(object(), ACTOR, env.user.id, [], version=1)  # type: ignore[arg-type]

    async def test_duplicate_ids_are_collapsed(self, env: SimpleNamespace) -> None:
        role = SimpleNamespace(id=uuid.uuid4(), code="editor", name="编辑", status="active", is_builtin=False)
        env.roles = [role]
        payload = await user_admin.replace_roles(object(), ACTOR, env.user.id, [role.id, role.id], version=1)  # type: ignore[arg-type]
        assert payload["role_ids"] == [str(role.id)]
        assert env.user.version == 2

    async def test_list_page_validates_sort_and_clamps_paging(
        self, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with pytest.raises(ApiError, match="排序"):
            await user_admin.list_users_page(object(), ACTOR, UserFilters(), page=1, page_size=20, sort="password")  # type: ignore[arg-type]
        role = SimpleNamespace(id=uuid.uuid4(), name="编辑", status="active", is_builtin=False)
        monkeypatch.setattr(user_admin.user_repo, "count_users", AsyncMock(return_value=1))
        listed = AsyncMock(return_value=[env.user])
        monkeypatch.setattr(user_admin.user_repo, "list_users", listed)
        monkeypatch.setattr(user_admin.user_repo, "roles_for_users", AsyncMock(return_value={env.user.id: [role]}))
        items, total = await user_admin.list_users_page(
            object(),  # type: ignore[arg-type]
            ACTOR,  # type: ignore[arg-type]
            UserFilters(),
            page=0,
            page_size=999,
            sort="username",  # type: ignore[arg-type]
        )
        assert total == 1
        assert items[0]["roles"][0]["name"] == "编辑"  # type: ignore[index]
        assert listed.await_args.kwargs == {"offset": 0, "limit": 100, "sort": "username"}

    async def test_get_user_lists_role_ids(self, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
        role = SimpleNamespace(id=uuid.uuid4(), name="编辑", status="active", is_builtin=False)
        monkeypatch.setattr(user_admin.user_repo, "roles_for_users", AsyncMock(return_value={env.user.id: [role]}))
        payload = await user_admin.get_user(object(), ACTOR, env.user.id)  # type: ignore[arg-type]
        assert payload["role_ids"] == [str(role.id)]
        assert payload["can_manage"] is True

    async def test_list_marks_superadmin_rows_unmanageable_for_a_user_admin(
        self, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """不是超级管理员的用户管理员：超级管理员那几行 can_manage=false，页面不给停用、删除、重置密码。"""

        boss = _user(username="admin")
        monkeypatch.setattr(user_admin.user_repo, "count_users", AsyncMock(return_value=2))
        monkeypatch.setattr(user_admin.user_repo, "list_users", AsyncMock(return_value=[env.user, boss]))
        monkeypatch.setattr(user_admin.user_repo, "roles_for_users", AsyncMock(return_value={}))
        monkeypatch.setattr(user_admin.user_repo, "builtin_superadmin_ids", AsyncMock(return_value={boss.id}))
        items, _ = await user_admin.list_users_page(
            object(),  # type: ignore[arg-type]
            ACTOR,  # type: ignore[arg-type]
            UserFilters(),
            page=1,
            page_size=20,
            sort="created_at",
        )
        assert [item["can_manage"] for item in items] == [True, False]
        env.superadmin_ids = {ACTOR.id}
        items, _ = await user_admin.list_users_page(
            object(),  # type: ignore[arg-type]
            ACTOR,  # type: ignore[arg-type]
            UserFilters(),
            page=1,
            page_size=20,
            sort="created_at",
        )
        assert [item["can_manage"] for item in items] == [True, True]


def test_temporary_passwords_always_pass_the_policy() -> None:
    """随机串偶尔没有数字，原来约 1.7% 的新建用户会被自己生成的密码拒掉。"""

    from app.application.user_fields import generate_temporary_password
    from app.domain.password import validate_password_policy

    assert all(validate_password_policy(generate_temporary_password()) is None for _ in range(2000))
