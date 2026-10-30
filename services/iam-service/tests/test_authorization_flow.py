"""本地权限判定：账号状态、资源是否发布、档位够不够，以及越权拒绝时的审计。仓储用替身。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.errors import PermissionDeniedError, UnauthenticatedError

from app.application import authorization, authz_catalog
from app.domain.authorization import AuthzDecision
from app.domain.enums import UserStatus

SOURCES_ID = uuid.uuid4()


def _resource(code: str, *, rid: uuid.UUID | None = None, published: bool = True, node_type: str = "resource") -> Any:
    return SimpleNamespace(id=rid or uuid.uuid4(), code=code, published=published, node_type=node_type)


def _user(**overrides: object) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "username": "zhangsan",
        "display_name": "张三",
        "status": UserStatus.ACTIVE,
        "must_change_password": False,
    }
    return SimpleNamespace(**(base | overrides))


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """资源目录和档位查询用替身；每个用例一份新的目录缓存和可拨动的时钟。"""

    state = SimpleNamespace(
        resources=[_resource("policy.sources", rid=SOURCES_ID)],
        actions=[
            SimpleNamespace(resource_id=SOURCES_ID, action_code="update", required_level="FULL"),
            SimpleNamespace(resource_id=SOURCES_ID, action_code="list", required_level="READ"),
            SimpleNamespace(resource_id=SOURCES_ID, action_code="purge", required_level="FULL"),
        ],
        level="FULL",
        superadmin=False,
        audit=AsyncMock(),
        clock=_Clock(),
    )
    state.list_resources = AsyncMock(side_effect=lambda *_: list(state.resources))
    state.list_actions = AsyncMock(side_effect=lambda *_: list(state.actions))
    state.effective_level = AsyncMock(side_effect=lambda *_: state.level)
    monkeypatch.setattr(authz_catalog.resource_repo, "list_all_resources", state.list_resources)
    monkeypatch.setattr(authz_catalog.resource_repo, "list_all_actions", state.list_actions)
    monkeypatch.setattr(authorization.resource_repo, "effective_level", state.effective_level)
    monkeypatch.setattr(authz_catalog, "catalog", authz_catalog.AuthzCatalog(clock=state.clock))
    monkeypatch.setattr(
        authorization.user_repo, "user_has_builtin_superadmin", AsyncMock(side_effect=lambda *_: state.superadmin)
    )
    monkeypatch.setattr(authorization, "enqueue_independent", state.audit)
    return state


async def _resolve(user: Any, code: str = "policy.sources", action: str = "update") -> tuple[AuthzDecision, Any]:
    return await authorization.resolve_authorization(object(), user, code, action)  # type: ignore[arg-type]


class TestResolve:
    async def test_enough_level_is_allowed(self, repo: SimpleNamespace) -> None:
        assert await _resolve(_user()) == (AuthzDecision.ALLOW, "FULL")
        repo.effective_level.assert_awaited_once()
        assert repo.effective_level.await_args.args[2] == SOURCES_ID

    async def test_unknown_resource_is_denied_even_if_a_level_exists(self, repo: SimpleNamespace) -> None:
        repo.resources = []
        decision, _ = await _resolve(_user())
        assert decision == AuthzDecision.DENY_UNKNOWN
        repo.effective_level.assert_not_awaited()

    async def test_unknown_action_is_denied_without_reading_levels(self, repo: SimpleNamespace) -> None:
        decision, _ = await _resolve(_user(), action="drop")
        assert decision == AuthzDecision.DENY_UNKNOWN
        repo.effective_level.assert_not_awaited()

    async def test_unpublished_resource_is_denied(self, repo: SimpleNamespace) -> None:
        repo.resources = [_resource("policy.sources", rid=SOURCES_ID, published=False)]
        decision, _ = await _resolve(_user())
        assert decision == AuthzDecision.DENY_UNPUBLISHED
        repo.effective_level.assert_not_awaited()

    async def test_directory_node_grants_nothing(self, repo: SimpleNamespace) -> None:
        repo.resources = [_resource("policy.sources", rid=SOURCES_ID, node_type="directory")]
        decision, level = await _resolve(_user())
        assert (decision, level) == (AuthzDecision.DENY_LEVEL, None)
        repo.effective_level.assert_not_awaited()

    async def test_disabled_account_is_denied(self, repo: SimpleNamespace) -> None:
        decision, _ = await _resolve(_user(status=UserStatus.DISABLED))
        assert decision == AuthzDecision.DENY_ACCOUNT
        repo.effective_level.assert_not_awaited()

    async def test_lower_level_is_denied(self, repo: SimpleNamespace) -> None:
        repo.level = "READ"
        assert not await authorization.is_allowed(object(), _user(), "policy.sources", "update")  # type: ignore[arg-type]


class TestCatalogCache:
    """资源和动作缓存在进程里：一次判定只剩查档位那一条；用户的角色和授权每次现查。"""

    async def test_catalog_is_read_once_and_levels_every_time(self, repo: SimpleNamespace) -> None:
        user = _user()
        for _ in range(3):
            await _resolve(user)
        assert repo.list_resources.await_count == 1
        assert repo.list_actions.await_count == 1
        assert repo.effective_level.await_count == 3

    async def test_revoked_level_takes_effect_on_the_next_check(self, repo: SimpleNamespace) -> None:
        user = _user()
        assert (await _resolve(user))[0] == AuthzDecision.ALLOW
        repo.level = None
        assert (await _resolve(user))[0] == AuthzDecision.DENY_LEVEL

    async def test_catalog_is_reread_after_the_ttl(self, repo: SimpleNamespace) -> None:
        await _resolve(_user())
        repo.resources = [_resource("policy.sources", rid=SOURCES_ID, published=False)]
        repo.clock.now += authz_catalog.CATALOG_TTL_SECONDS - 1
        assert (await _resolve(_user()))[0] == AuthzDecision.ALLOW
        repo.clock.now += 2
        assert (await _resolve(_user()))[0] == AuthzDecision.DENY_UNPUBLISHED
        assert repo.list_resources.await_count == 2

    async def test_a_new_resource_is_picked_up_without_waiting_for_the_ttl(self, repo: SimpleNamespace) -> None:
        await _resolve(_user())
        new_id = uuid.uuid4()
        repo.resources = [*repo.resources, _resource("policy.new", rid=new_id)]
        repo.actions = [*repo.actions, SimpleNamespace(resource_id=new_id, action_code="list", required_level="READ")]
        repo.clock.now += authz_catalog.MISS_RELOAD_SECONDS
        assert (await _resolve(_user(), "policy.new", "list"))[0] == AuthzDecision.ALLOW

    async def test_a_new_action_on_a_known_resource_is_picked_up_without_waiting(self, repo: SimpleNamespace) -> None:
        """部署时给已有模块加了新动作：原来资源查得到就不重读，最多一分钟里连超管调新动作都被拒。"""

        await _resolve(_user())
        repo.actions = [
            *repo.actions,
            SimpleNamespace(resource_id=SOURCES_ID, action_code="sync", required_level="FULL"),
        ]
        repo.clock.now += authz_catalog.MISS_RELOAD_SECONDS
        assert (await _resolve(_user(), "policy.sources", "sync"))[0] == AuthzDecision.ALLOW
        assert repo.list_resources.await_count == 2

    async def test_unknown_codes_do_not_hit_the_database_every_time(self, repo: SimpleNamespace) -> None:
        await _resolve(_user())
        for _ in range(5):
            assert (await _resolve(_user(), "no.such"))[0] == AuthzDecision.DENY_UNKNOWN
        assert repo.list_resources.await_count == 1
        repo.clock.now += authz_catalog.MISS_RELOAD_SECONDS
        await _resolve(_user(), "no.such")
        assert repo.list_resources.await_count == 2

    async def test_invalidate_forces_a_reread(self, repo: SimpleNamespace) -> None:
        await _resolve(_user())
        authz_catalog.catalog.invalidate()
        await _resolve(_user())
        assert repo.list_resources.await_count == 2


class TestAssertAllowed:
    async def test_allowed_returns_the_level_without_audit(self, repo: SimpleNamespace) -> None:
        assert await authorization.assert_allowed(object(), _user(), "policy.sources", "update") == "FULL"  # type: ignore[arg-type]
        repo.audit.assert_not_awaited()

    async def test_denied_write_leaves_an_audit_trail(self, repo: SimpleNamespace) -> None:
        repo.level = None
        with pytest.raises(PermissionDeniedError, match="没有执行该操作的权限"):
            await authorization.assert_allowed(object(), _user(), "policy.sources", "update")  # type: ignore[arg-type]
        payload = repo.audit.await_args.kwargs["payload"]
        assert payload["reason"] == "deny_level"
        assert payload["action_code"] == "update"

    async def test_denied_read_is_not_audited(self, repo: SimpleNamespace) -> None:
        repo.level = None
        with pytest.raises(PermissionDeniedError):
            await authorization.assert_allowed(object(), _user(), "policy.sources", "list")  # type: ignore[arg-type]
        repo.audit.assert_not_awaited()

    async def test_audit_failure_does_not_change_the_denial(self, repo: SimpleNamespace) -> None:
        repo.level = None
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


async def test_service_denials_are_audited_once_per_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """业务服务问 IAM 被拒要留审计；同一个人、同一模块、同一动作 10 分钟只记一次，轮询不刷屏。"""

    class _Redis:
        def __init__(self) -> None:
            self.keys: dict[str, int] = {}

        async def set(self, key: str, _value: str, *, nx: bool, ex: int) -> bool:
            if nx and key in self.keys:
                return False
            self.keys[key] = ex
            return True

    events: list[dict[str, Any]] = []

    async def enqueue(*, event_type: str, payload: dict[str, Any]) -> None:
        events.append({"type": event_type, **payload})

    monkeypatch.setattr(authorization, "enqueue_independent", enqueue)
    redis, user = _Redis(), _user()
    context = {"resource": "policy.sources", "action": "delete", "reason": "没有执行该操作的权限"}
    for _ in range(3):
        await authorization.audit_service_denial(redis, user, context, "policy-service")  # type: ignore[arg-type]
    assert [(item["type"], item["resource_code"], item["caller"]) for item in events] == [
        ("iam.authz.denied", "policy.sources", "policy-service")
    ]
    assert list(redis.keys.values()) == [authorization.DENIAL_AUDIT_SECONDS]

    async def broken(**_: Any) -> None:
        raise RuntimeError("outbox down")

    monkeypatch.setattr(authorization, "enqueue_independent", broken)
    other = {**context, "action": "update"}
    await authorization.audit_service_denial(redis, user, other, "policy-service")  # type: ignore[arg-type]  # 写不进去也不抛
