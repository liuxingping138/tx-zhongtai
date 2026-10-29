"""用户逻辑删除：人从列表消失，不能登录，记录留着，用户名可以再用。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from platform_common.errors import NotFoundError, PermissionDeniedError, UnauthenticatedError
from sqlalchemy import select

from app.application import auth_service as auth_module
from app.application import user_admin
from app.application.auth_service import UNIFIED_LOGIN_FAILURE, AuthService
from app.domain.enums import UserStatus
from app.domain.filters import UserFilters
from app.domain.models import User
from app.domain.password import hash_password
from app.repositories.users import _apply_user_filters


def test_user_list_always_excludes_deleted() -> None:
    stmt = _apply_user_filters(select(User), UserFilters(status=["disabled", "deleted"]))
    values = list(stmt.compile().params.values())
    # 排除条件带一次 deleted；传进来的 deleted 不会进入筛选列表。
    assert values.count(UserStatus.DELETED) == 1
    assert ["disabled"] in values


@pytest.mark.asyncio
async def test_delete_user_keeps_the_row_and_revokes_access(monkeypatch: pytest.MonkeyPatch) -> None:
    user = SimpleNamespace(id=uuid.uuid4(), status=UserStatus.ACTIVE, version=3, username="areaonly")
    actor = SimpleNamespace(id=uuid.uuid4())
    events: list[str] = []

    async def get_for_update(_session: object, _user_id: uuid.UUID) -> object:
        return user

    async def enqueue(_session: object, *, event_type: str, payload: dict[str, object]) -> None:
        events.append(event_type)
        assert payload["username"] == "areaonly"

    monkeypatch.setattr(user_admin, "assert_can_manage_target", AsyncMock())
    monkeypatch.setattr(user_admin, "_guard_last_superadmin", AsyncMock())
    monkeypatch.setattr(user_admin.user_repo, "get_user_for_update", get_for_update)
    monkeypatch.setattr(user_admin.user_repo, "clear_user_roles", AsyncMock())
    monkeypatch.setattr(user_admin.grant_repo, "clear_for_user", AsyncMock())
    monkeypatch.setattr(user_admin.session_repo, "revoke_user_sessions", AsyncMock())
    monkeypatch.setattr(user_admin.outbox_repo, "enqueue", enqueue)

    await user_admin.delete_user(SimpleNamespace(), actor, user.id)

    assert user.status == UserStatus.DELETED
    assert user.version == 4
    assert events == ["iam.user.deleted"]
    user_admin.session_repo.revoke_user_sessions.assert_awaited()  # type: ignore[attr-defined]
    user_admin.user_repo.clear_user_roles.assert_awaited()  # type: ignore[attr-defined]
    user_admin.grant_repo.clear_for_user.assert_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_cannot_delete_the_account_you_are_using() -> None:
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, status=UserStatus.ACTIVE, version=1, username="me")

    async def get_for_update(_session: object, _user_id: uuid.UUID) -> object:
        return user

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(user_admin.user_repo, "get_user_for_update", get_for_update)
    with pytest.raises(PermissionDeniedError, match="当前登录"):
        await user_admin.delete_user(SimpleNamespace(), SimpleNamespace(id=user_id), user_id)
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_cannot_delete_the_last_superadmin(monkeypatch: pytest.MonkeyPatch) -> None:
    target = SimpleNamespace(id=uuid.uuid4(), status=UserStatus.ACTIVE, version=1, username="admin")
    actor = SimpleNamespace(id=uuid.uuid4())

    async def get_for_update(_session: object, _user_id: uuid.UUID) -> object:
        return target

    async def lock(_session: object) -> list[object]:
        return [SimpleNamespace(id=target.id, status=UserStatus.ACTIVE)]

    monkeypatch.setattr(user_admin.user_repo, "get_user_for_update", get_for_update)
    monkeypatch.setattr(user_admin.user_repo, "user_has_builtin_superadmin", AsyncMock(return_value=True))
    monkeypatch.setattr(user_admin.user_repo, "lock_superadmin_users", lock)
    monkeypatch.setattr(user_admin, "enqueue_independent", AsyncMock())

    with pytest.raises(PermissionDeniedError, match="最后一个可登录超级管理员"):
        await user_admin.delete_user(SimpleNamespace(), actor, target.id)
    assert target.status == UserStatus.ACTIVE


@pytest.mark.asyncio
async def test_deleted_account_login_looks_like_a_wrong_password(monkeypatch: pytest.MonkeyPatch) -> None:
    user = SimpleNamespace(
        username="gone",
        password_hash=hash_password("correct-horse-1"),
        status=UserStatus.DELETED,
    )

    async def fake_get(_session: object, _username: str) -> object:
        return user

    monkeypatch.setattr(auth_module.user_repo, "get_user_by_username", fake_get)
    service = AuthService(session=SimpleNamespace(), settings=SimpleNamespace())
    with pytest.raises(UnauthenticatedError, match=UNIFIED_LOGIN_FAILURE):
        await service.authenticate_password("gone", "correct-horse-1")


def test_deleted_user_is_not_found() -> None:
    with pytest.raises(NotFoundError, match="用户不存在"):
        user_admin._require_live(SimpleNamespace(status=UserStatus.DELETED))
