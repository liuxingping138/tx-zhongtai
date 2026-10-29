"""单独给人授权：和角色同一套规则，「权限分配」不能单独给人，改动进审计。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.errors import ApiError, NotFoundError, PermissionDeniedError

from app.application import user_grants
from app.domain.enums import NodeType, UserStatus

RESOURCES = {
    "policy.sources": SimpleNamespace(
        id=uuid.uuid4(), code="policy.sources", published=True, node_type=NodeType.RESOURCE
    ),
    "system.permissions": SimpleNamespace(
        id=uuid.uuid4(), code="system.permissions", published=True, node_type=NodeType.RESOURCE
    ),
    "policy": SimpleNamespace(id=uuid.uuid4(), code="policy", published=True, node_type=NodeType.DIRECTORY),
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    user = SimpleNamespace(id=uuid.uuid4(), status=UserStatus.ACTIVE, version=1, updated_at=None)
    state = SimpleNamespace(user=user, saved=None, events=[])
    monkeypatch.setattr(user_grants.user_repo, "get_user_by_id", AsyncMock(side_effect=lambda *_: state.user))
    monkeypatch.setattr(user_grants.user_repo, "get_user_for_update", AsyncMock(side_effect=lambda *_: state.user))
    monkeypatch.setattr(user_grants, "assert_can_manage_target", AsyncMock())
    monkeypatch.setattr(
        user_grants.resource_repo, "get_resource_by_code", AsyncMock(side_effect=lambda _s, code: RESOURCES.get(code))
    )

    async def _replace(_session: object, _user_id: uuid.UUID, grants: list[Any], *, updated_by: uuid.UUID) -> None:
        state.saved = grants

    monkeypatch.setattr(user_grants.grant_repo, "replace_for_user", _replace)
    monkeypatch.setattr(user_grants.grant_repo, "list_for_user", AsyncMock(return_value=[]))

    async def _enqueue(_session: object, *, event_type: str, payload: dict[str, object]) -> None:
        state.events.append(event_type)

    monkeypatch.setattr(user_grants.outbox_repo, "enqueue", _enqueue)
    return state


async def _replace(env: SimpleNamespace, grants: list[tuple[str, str]]) -> None:
    await user_grants.replace_grants(object(), SimpleNamespace(id=uuid.uuid4()), env.user.id, grants)  # type: ignore[arg-type]


async def test_none_levels_are_dropped_and_the_change_is_audited(env: SimpleNamespace) -> None:
    await _replace(env, [("policy.sources", "EXPORT"), ("policy.sources", "NONE")])
    assert env.saved == [(RESOURCES["policy.sources"].id, "EXPORT")]
    assert env.events == ["iam.user.grants_replaced"]


async def test_grant_permission_never_goes_to_a_person(env: SimpleNamespace) -> None:
    with pytest.raises(PermissionDeniedError, match="权限分配"):
        await _replace(env, [("system.permissions", "READ")])
    assert env.saved is None


@pytest.mark.parametrize(
    ("code", "level", "error"),
    [
        ("policy", "READ", PermissionDeniedError),
        ("nope", "READ", PermissionDeniedError),
        ("policy.sources", "ADMIN", ApiError),
    ],
)
async def test_directories_unknown_modules_and_bad_levels_are_rejected(
    env: SimpleNamespace, code: str, level: str, error: type[Exception]
) -> None:
    with pytest.raises(error):
        await _replace(env, [(code, level)])


async def test_deleted_users_cannot_be_granted(env: SimpleNamespace) -> None:
    env.user = SimpleNamespace(id=env.user.id, status=UserStatus.DELETED)
    with pytest.raises(NotFoundError):
        await _replace(env, [("policy.sources", "READ")])


async def test_concurrent_edits_conflict_and_duplicate_modules_are_rejected(env: SimpleNamespace) -> None:
    """单独授权原来不带版本号：两人同时改同一个人，后保存的悄悄盖掉先保存的；同一模块提交两次撞主键 500。"""

    from platform_common.errors import VersionConflictError

    with pytest.raises(VersionConflictError):
        await user_grants.replace_grants(
            object(),  # type: ignore[arg-type]
            SimpleNamespace(id=uuid.uuid4()),  # type: ignore[arg-type]
            env.user.id,
            [("policy.sources", "READ")],
            version=0,
        )
    with pytest.raises(ApiError, match="出现了两次"):
        await _replace(env, [("policy.sources", "READ"), ("policy.sources", "FULL")])
    await _replace(env, [("policy.sources", "READ")])
    assert env.user.version == 2  # 改了授权，版本号跟着走，另一个人手里的旧版本就会被拦下
