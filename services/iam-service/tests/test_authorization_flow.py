"""本地权限判定：账号状态、资源是否发布、档位够不够，以及越权拒绝时的审计。仓储用替身。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from platform_common.errors import PermissionDeniedError, UnauthenticatedError

from app.application import authorization
from app.domain.authorization import AuthzDecision
from app.domain.enums import UserStatus

RESOURCE = SimpleNamespace(id=uuid.uuid4(), published=True)
ACTION = SimpleNamespace(required_level="FULL")


def _user(**overrides: object) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "username": "zhangsan",
        "display_name": "张三",
        "status": UserStatus.ACTIVE,
        "must_change_password": False,
    }
    return SimpleNamespace(**(base | overrides))


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(
        resource=RESOURCE,
        action=ACTION,
        levels={"policy.sources": "FULL"},
        superadmin=False,
        audit=AsyncMock(),
    )
    monkeypatch.setattr(
        authorization.resource_repo, "get_resource_by_code", AsyncMock(side_effect=lambda *_: state.resource)
    )
    monkeypatch.setattr(authorization.resource_repo, "get_action", AsyncMock(side_effect=lambda *_: state.action))
    monkeypatch.setattr(
        authorization.resource_repo, "list_effective_levels", AsyncMock(side_effect=lambda *_: state.levels)
    )
    monkeypatch.setattr(
        authorization.user_repo, "user_has_builtin_superadmin", AsyncMock(side_effect=lambda *_: state.superadmin)
    )
    monkeypatch.setattr(authorization, "enqueue_independent", state.audit)
    return state


class TestResolve:
    async def test_enough_level_is_allowed(self, repo: SimpleNamespace) -> None:
        decision, level = await authorization.resolve_authorization(object(), _user(), "policy.sources", "update")  # type: ignore[arg-type]
        assert (decision, level) == (AuthzDecision.ALLOW, "FULL")

    async def test_unknown_resource_is_denied_even_if_a_level_exists(self, repo: SimpleNamespace) -> None:
        repo.resource = None
        decision, _ = await authorization.resolve_authorization(object(), _user(), "policy.sources", "update")  # type: ignore[arg-type]
        assert decision == AuthzDecision.DENY_UNKNOWN

    async def test_disabled_account_is_denied(self, repo: SimpleNamespace) -> None:
        decision, _ = await authorization.resolve_authorization(
            object(),
            _user(status=UserStatus.DISABLED),
            "policy.sources",
            "update",  # type: ignore[arg-type]
        )
        assert decision == AuthzDecision.DENY_ACCOUNT

    async def test_lower_level_is_denied(self, repo: SimpleNamespace) -> None:
        repo.levels = {"policy.sources": "READ"}
        assert not await authorization.is_allowed(object(), _user(), "policy.sources", "update")  # type: ignore[arg-type]


class TestAssertAllowed:
    async def test_allowed_returns_the_level_without_audit(self, repo: SimpleNamespace) -> None:
        assert await authorization.assert_allowed(object(), _user(), "policy.sources", "update") == "FULL"  # type: ignore[arg-type]
        repo.audit.assert_not_awaited()

    async def test_denied_write_leaves_an_audit_trail(self, repo: SimpleNamespace) -> None:
        repo.levels = {}
        with pytest.raises(PermissionDeniedError, match="没有执行该操作的权限"):
            await authorization.assert_allowed(object(), _user(), "policy.sources", "update")  # type: ignore[arg-type]
        payload = repo.audit.await_args.kwargs["payload"]
        assert payload["reason"] == "deny_level"
        assert payload["action_code"] == "update"

    async def test_denied_read_is_not_audited(self, repo: SimpleNamespace) -> None:
        repo.levels = {}
        with pytest.raises(PermissionDeniedError):
            await authorization.assert_allowed(object(), _user(), "policy.sources", "list")  # type: ignore[arg-type]
        repo.audit.assert_not_awaited()

    async def test_audit_failure_does_not_change_the_denial(self, repo: SimpleNamespace) -> None:
        repo.levels = {}
        repo.audit.side_effect = RuntimeError("outbox down")
        with pytest.raises(PermissionDeniedError, match="没有执行该操作的权限"):
            await authorization.assert_allowed(object(), _user(), "policy.sources", "update")  # type: ignore[arg-type]


class TestAccessContext:
    async def test_disabled_account_is_unauthenticated(self, repo: SimpleNamespace) -> None:
        with pytest.raises(UnauthenticatedError):
            await authorization.authorize_access_context(
                object(),
                _user(status=UserStatus.DISABLED),
                "policy.sources",
                "update",  # type: ignore[arg-type]
            )

    async def test_initial_password_must_be_changed_first(self, repo: SimpleNamespace) -> None:
        with pytest.raises(PermissionDeniedError, match="修改初始密码"):
            await authorization.authorize_access_context(
                object(),
                _user(must_change_password=True),
                "policy.sources",
                "update",  # type: ignore[arg-type]
            )

    async def test_allowed_context_describes_the_user(self, repo: SimpleNamespace) -> None:
        result = await authorization.authorize_access_context(object(), _user(), "policy.sources", "update")  # type: ignore[arg-type]
        assert result["allowed"] is True
        assert result["level"] == "FULL"
        assert result["user"]["username"] == "zhangsan"  # type: ignore[index]

    async def test_purge_needs_the_builtin_superadmin_even_with_full(self, repo: SimpleNamespace) -> None:
        repo.action = SimpleNamespace(required_level="FULL")
        denied = await authorization.authorize_access_context(object(), _user(), "policy.sources", "purge")  # type: ignore[arg-type]
        assert denied["allowed"] is False
        assert denied["reason"] == "仅超级管理员可清空数据"
        repo.superadmin = True
        allowed = await authorization.authorize_access_context(object(), _user(), "policy.sources", "purge")  # type: ignore[arg-type]
        assert allowed["allowed"] is True


class TestVisiblePermissions:
    async def test_menus_follow_published_resources_the_user_can_reach(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sources = SimpleNamespace(id=uuid.uuid4(), code="policy.sources", published=True)
        hidden = SimpleNamespace(id=uuid.uuid4(), code="policy.tags", published=True)
        draft = SimpleNamespace(id=uuid.uuid4(), code="customer", published=False)
        now = datetime.now(UTC)

        def menu(title: str, resource_id: uuid.UUID | None, enabled: bool = True) -> SimpleNamespace:
            return SimpleNamespace(
                id=uuid.uuid4(),
                parent_id=None,
                title=title,
                route_name=title,
                resource_id=resource_id,
                icon=None,
                sort_order=1,
                enabled=enabled,
                created_at=now,
            )

        menus = [
            menu("政策", None),
            menu("信源", sources.id),
            menu("标签", hidden.id),
            menu("客户", draft.id),
            menu("停用", sources.id, enabled=False),
        ]
        monkeypatch.setattr(
            authorization.resource_repo, "list_effective_levels", AsyncMock(return_value={"policy.sources": "READ"})
        )
        monkeypatch.setattr(
            authorization.resource_repo, "list_all_resources", AsyncMock(return_value=[sources, hidden, draft])
        )
        monkeypatch.setattr(authorization.resource_repo, "list_all_menus", AsyncMock(return_value=menus))

        result = await authorization.visible_permissions(object(), uuid.uuid4())  # type: ignore[arg-type]

        assert [item["title"] for item in result["menus"]] == ["政策", "信源"]  # type: ignore[attr-defined]
        assert result["resources"] == [{"code": "policy.sources", "level": "READ"}]
