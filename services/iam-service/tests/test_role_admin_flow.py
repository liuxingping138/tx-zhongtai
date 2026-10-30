"""角色与授权用例：新建、改状态、替换授权的各道门槛，以及复制角色时不带走「权限分配」。仓储用替身。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from platform_common.errors import ApiError, NotFoundError, PermissionDeniedError, VersionConflictError
from sqlalchemy.exc import IntegrityError

from app.application import role_admin
from app.application.role_admin import RoleChanges
from app.domain.catalog import SUPERADMIN_ROLE_CODE
from app.domain.enums import NodeType

NOW = datetime(2026, 10, 1, tzinfo=UTC)
ACTOR = SimpleNamespace(id=uuid.uuid4())


def _role(**overrides: Any) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "code": "editor",
        "name": "编辑",
        "description": "",
        "status": "active",
        "is_builtin": False,
        "version": 1,
        "created_at": NOW,
        "updated_at": NOW,
    }
    return SimpleNamespace(**(base | overrides))


def _resource(code: str, **overrides: Any) -> SimpleNamespace:
    base = {"id": uuid.uuid4(), "code": code, "name": code, "published": True, "node_type": NodeType.RESOURCE}
    return SimpleNamespace(**(base | overrides))


class _Session:
    def __init__(self, flush_error: Exception | None = None) -> None:
        self.added: list[Any] = []
        self.flush = AsyncMock(side_effect=flush_error)

    def add(self, row: Any) -> None:
        self.added.append(row)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(role=_role(), events=[], denied=[], resources={}, grants=[], replaced=None)

    async def enqueue(_s: object, *, event_type: str, payload: dict[str, object]) -> None:
        state.events.append(event_type)

    async def denied(*, event_type: str, payload: dict[str, object]) -> None:
        state.denied.append(event_type)

    async def replace(_s: object, role_id: uuid.UUID, pairs: list[Any], *, updated_by: uuid.UUID) -> None:
        state.replaced = pairs

    monkeypatch.setattr(role_admin.outbox_repo, "enqueue", enqueue)
    monkeypatch.setattr(role_admin, "enqueue_independent", denied)
    monkeypatch.setattr(role_admin.role_repo, "get_role_for_update", AsyncMock(side_effect=lambda *_: state.role))
    monkeypatch.setattr(role_admin.role_repo, "get_role_by_id", AsyncMock(side_effect=lambda *_: state.role))
    monkeypatch.setattr(role_admin.role_repo, "replace_role_grants", replace)
    monkeypatch.setattr(role_admin.role_repo, "list_role_grants", AsyncMock(side_effect=lambda *_: state.grants))
    monkeypatch.setattr(role_admin.role_repo, "member_counts", AsyncMock(return_value={}))
    monkeypatch.setattr(role_admin.role_repo, "grant_level_counts", AsyncMock(return_value={}))
    monkeypatch.setattr(
        role_admin.resource_repo,
        "get_resource_by_code",
        AsyncMock(side_effect=lambda _s, code: state.resources.get(code)),
    )
    return state


class TestCreateRole:
    async def test_code_is_generated_when_omitted(self, env: SimpleNamespace) -> None:
        session = _Session()
        payload = await role_admin.create_role(session, ACTOR, code=None, name=" 运营 ")  # type: ignore[arg-type]
        assert payload["name"] == "运营"
        assert str(payload["code"]).startswith("role-")
        assert payload["is_builtin"] is False
        assert env.events == ["iam.role.created"]

    @pytest.mark.parametrize("code", ["1abc", "Has Space", "a"])
    async def test_malformed_code_is_rejected(self, env: SimpleNamespace, code: str) -> None:
        with pytest.raises(ApiError, match="角色编码"):
            await role_admin.create_role(_Session(), ACTOR, code=code, name="运营")  # type: ignore[arg-type]

    async def test_blank_name_and_overlong_description_are_rejected(self, env: SimpleNamespace) -> None:
        with pytest.raises(ApiError, match="名称"):
            await role_admin.create_role(_Session(), ACTOR, code=None, name=" ")  # type: ignore[arg-type]
        with pytest.raises(ApiError, match="不能超过"):
            await role_admin.create_role(_Session(), ACTOR, code=None, name="运营", description="x" * 501)  # type: ignore[arg-type]

    async def test_duplicate_code_is_a_conflict(self, env: SimpleNamespace) -> None:
        session = _Session(flush_error=IntegrityError("insert", {}, Exception("unique")))
        with pytest.raises(VersionConflictError, match="编码已存在"):
            await role_admin.create_role(session, ACTOR, code="ops", name="运营")  # type: ignore[arg-type]


class TestUpdateRole:
    async def test_missing_role_and_stale_version(self, env: SimpleNamespace) -> None:
        with pytest.raises(VersionConflictError):
            await role_admin.update_role(object(), ACTOR, env.role.id, RoleChanges(version=3))  # type: ignore[arg-type]
        env.role = None
        with pytest.raises(NotFoundError):
            await role_admin.update_role(object(), ACTOR, uuid.uuid4(), RoleChanges(version=1))  # type: ignore[arg-type]

    async def test_name_description_and_status_are_applied(self, env: SimpleNamespace) -> None:
        payload = await role_admin.update_role(
            object(),
            ACTOR,
            env.role.id,  # type: ignore[arg-type]
            RoleChanges(version=1, name=" 主编 ", description="负责审核", status="disabled"),
        )
        assert (payload["name"], payload["description"], payload["status"], payload["version"]) == (
            "主编",
            "负责审核",
            "disabled",
            2,
        )

    async def test_builtin_role_status_is_locked(self, env: SimpleNamespace) -> None:
        env.role = _role(is_builtin=True)
        with pytest.raises(PermissionDeniedError, match="内置角色"):
            await role_admin.update_role(object(), ACTOR, env.role.id, RoleChanges(version=1, status="disabled"))  # type: ignore[arg-type]

    async def test_enabling_a_disabled_role_needs_the_grant_permission(self, env: SimpleNamespace) -> None:
        """启用停用的角色等于把授权还给它的全部成员：和分配角色一样，只有超管（权限分配）能做。"""

        env.role.status = "disabled"
        with pytest.raises(PermissionDeniedError, match="权限分配"):
            await role_admin.update_role(object(), ACTOR, env.role.id, RoleChanges(version=1, status="active"))  # type: ignore[arg-type]
        payload = await role_admin.update_role(
            object(),
            ACTOR,
            env.role.id,  # type: ignore[arg-type]
            RoleChanges(version=1, status="active"),
            can_grant=True,
        )
        assert payload["status"] == "active"
        # 已经启用的角色改名、改说明时带着 active 不算「启用」。
        await role_admin.update_role(object(), ACTOR, env.role.id, RoleChanges(version=2, name="新名", status="active"))  # type: ignore[arg-type]

    async def test_invalid_status_is_rejected(self, env: SimpleNamespace) -> None:
        with pytest.raises(ApiError, match="无效的角色状态"):
            await role_admin.update_role(object(), ACTOR, env.role.id, RoleChanges(version=1, status="archived"))  # type: ignore[arg-type]


class TestReplaceGrants:
    async def test_superadmin_role_grants_are_fixed(self, env: SimpleNamespace) -> None:
        env.role = _role(is_builtin=True, code=SUPERADMIN_ROLE_CODE)
        with pytest.raises(PermissionDeniedError, match="固定拥有全部权限"):
            await role_admin.replace_grants(object(), ACTOR, env.role.id, version=1, grants=[])  # type: ignore[arg-type]

    async def test_none_level_is_skipped_and_known_levels_are_stored(self, env: SimpleNamespace) -> None:
        env.resources = {"policy.sources": _resource("policy.sources")}
        await role_admin.replace_grants(
            object(),
            ACTOR,
            env.role.id,
            version=1,  # type: ignore[arg-type]
            grants=[("policy.sources", "READ"), ("codebook.scenarios", "NONE")],
        )
        assert env.replaced == [(env.resources["policy.sources"].id, "READ")]
        assert env.role.version == 2
        assert env.events == ["iam.role.grants_replaced"]

    async def test_bad_level_unknown_and_unpublished_resources_are_refused(self, env: SimpleNamespace) -> None:
        env.resources = {
            "draft": _resource("draft", published=False),
            "dir": _resource("dir", node_type=NodeType.DIRECTORY),
        }
        with pytest.raises(ApiError, match="授权等级无效"):
            await role_admin.replace_grants(object(), ACTOR, env.role.id, version=1, grants=[("draft", "ADMIN")])  # type: ignore[arg-type]
        with pytest.raises(PermissionDeniedError, match="未知资源"):
            await role_admin.replace_grants(object(), ACTOR, env.role.id, version=1, grants=[("nope", "READ")])  # type: ignore[arg-type]
        for code in ("draft", "dir"):
            with pytest.raises(PermissionDeniedError, match="未发布资源或目录"):
                await role_admin.replace_grants(object(), ACTOR, env.role.id, version=1, grants=[(code, "READ")])  # type: ignore[arg-type]
        assert env.denied == ["iam.role.grant_denied"] * 2
        assert env.replaced is None

    async def test_permission_assignment_only_goes_to_the_superadmin_role(self, env: SimpleNamespace) -> None:
        env.resources = {"system.permissions": _resource("system.permissions")}
        with pytest.raises(PermissionDeniedError, match="仅能授予超级管理员"):
            await role_admin.replace_grants(
                object(), ACTOR, env.role.id, version=1, grants=[("system.permissions", "FULL")]
            )  # type: ignore[arg-type]


class TestCopyRole:
    async def test_copy_keeps_grants_but_drops_permission_assignment_and_unpublished(
        self, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = _role(code="source")
        sources, perms, draft = (
            _resource("policy.sources"),
            _resource("system.permissions"),
            _resource("x", published=False),
        )
        env.resources = {"policy.sources": sources}
        env.grants = [
            (SimpleNamespace(level="EXPORT"), sources),
            (SimpleNamespace(level="FULL"), perms),
            (SimpleNamespace(level="READ"), draft),
        ]
        created = _role(code="role-new", name="副本")
        monkeypatch.setattr(role_admin, "create_role", AsyncMock(return_value=role_admin.role_public(created)))
        monkeypatch.setattr(
            role_admin.role_repo,
            "get_role_by_id",
            AsyncMock(side_effect=lambda _s, rid: source if rid == source.id else created),
        )
        replaced = AsyncMock(return_value={})
        monkeypatch.setattr(role_admin, "replace_grants", replaced)
        monkeypatch.setattr(role_admin, "get_role", AsyncMock(return_value={"id": str(created.id)}))

        await role_admin.copy_role(object(), ACTOR, source.id, name="副本")  # type: ignore[arg-type]

        assert replaced.await_args.kwargs["grants"] == [("policy.sources", "EXPORT")]

    async def test_copy_of_missing_role_is_not_found(self, env: SimpleNamespace) -> None:
        env.role = None
        with pytest.raises(NotFoundError):
            await role_admin.copy_role(object(), ACTOR, uuid.uuid4(), name="副本")  # type: ignore[arg-type]


class TestQueries:
    async def test_get_role_adds_member_and_grant_counts(
        self, env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(role_admin.role_repo, "member_counts", AsyncMock(return_value={env.role.id: 3}))
        monkeypatch.setattr(
            role_admin.role_repo, "grant_level_counts", AsyncMock(return_value={env.role.id: {"READ": 2, "FULL": 1}})
        )
        payload = await role_admin.get_role(object(), env.role.id)  # type: ignore[arg-type]
        assert payload["member_count"] == 3
        assert payload["grant_counts"] == {"read": 2, "export": 0, "full": 1}

    async def test_members_and_grants_of_missing_role(self, env: SimpleNamespace) -> None:
        env.role = None
        with pytest.raises(NotFoundError):
            await role_admin.list_members(object(), uuid.uuid4())  # type: ignore[arg-type]
        with pytest.raises(NotFoundError):
            await role_admin.list_grants(object(), uuid.uuid4())  # type: ignore[arg-type]

    async def test_list_grants_names_the_resources(self, env: SimpleNamespace) -> None:
        sources = _resource("policy.sources")
        env.grants = [(SimpleNamespace(level="READ"), sources)]
        payload = await role_admin.list_grants(object(), env.role.id)  # type: ignore[arg-type]
        assert payload["grants"] == [
            {"resource_code": "policy.sources", "resource_name": "policy.sources", "level": "READ"}
        ]

    async def test_resource_tree_nests_children_and_sorts_actions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parent = _resource(
            "policy", node_type=NodeType.DIRECTORY, service_code="policy-service", sort_order=1, parent_id=None
        )
        child = _resource("policy.sources", service_code="policy-service", sort_order=2, parent_id=parent.id)
        actions = [
            SimpleNamespace(resource_id=child.id, action_code="update", required_level="FULL"),
            SimpleNamespace(resource_id=child.id, action_code="list", required_level="READ"),
        ]
        monkeypatch.setattr(role_admin.resource_repo, "list_all_resources", AsyncMock(return_value=[parent, child]))
        monkeypatch.setattr(role_admin.resource_repo, "list_all_actions", AsyncMock(return_value=actions))

        tree = await role_admin.resource_tree(object())  # type: ignore[arg-type]

        assert [node["code"] for node in tree] == ["policy"]
        nested = tree[0]["children"][0]  # type: ignore[index]
        assert nested["code"] == "policy.sources"
        assert [a["action_code"] for a in nested["actions"]] == ["list", "update"]


def test_grant_changes_list_only_modules_whose_level_moved() -> None:
    """角色授权的审计记哪个模块从哪档到哪档：原来只记「改了几项」，追查不了谁开了什么。"""

    before = {"policy.sources": ("信源管理", "READ"), "ai.prompts": ("提示词模板", "FULL")}
    after = {
        "policy.sources": ("信源管理", "EXPORT"),
        "ai.prompts": ("提示词模板", "FULL"),
        "ai.chat": ("多轮对话", "READ"),
    }
    assert role_admin.grant_changes(before, after) == [
        {"module": "多轮对话", "code": "ai.chat", "from": "NONE", "to": "READ"},
        {"module": "信源管理", "code": "policy.sources", "from": "READ", "to": "EXPORT"},
    ]
    assert role_admin.grant_changes(before, {}) == [
        {"module": "提示词模板", "code": "ai.prompts", "from": "FULL", "to": "NONE"},
        {"module": "信源管理", "code": "policy.sources", "from": "READ", "to": "NONE"},
    ]
