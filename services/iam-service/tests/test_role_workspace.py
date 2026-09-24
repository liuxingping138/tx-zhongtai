"""角色与权限工作台：自动编码、复制角色、成员增删、实际权限、建账号即分配角色的权限门槛。"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("IAM_DATABASE_URL", "postgresql+asyncpg://iam_app:test@localhost:5432/iam_db")
os.environ.setdefault("IAM_REDIS_URL", "redis://localhost:6379/0")

import pytest  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

from app.api.schemas import RoleCreateRequest, UserCreateRequest  # noqa: E402
from app.application import role_admin, user_admin  # noqa: E402
from app.main import app  # noqa: E402


def _role(name: str, status: str = "active", code: str = "r") -> SimpleNamespace:
    now = datetime(2026, 9, 23, tzinfo=UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        code=code,
        name=name,
        description="",
        status=status,
        is_builtin=False,
        version=1,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_create_role_generates_code_when_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    monkeypatch.setattr(role_admin.outbox_repo, "enqueue", AsyncMock())
    actor = SimpleNamespace(id=uuid.uuid4())
    created = await role_admin.create_role(session, actor, code=None, name="政策数据管理员", description=" 维护政策表 ")
    assert str(created["code"]).startswith("role-")
    assert created["description"] == "维护政策表"


@pytest.mark.asyncio
async def test_create_role_rejects_bad_code_with_readable_message(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(Exception, match="小写字母开头"):
        await role_admin.create_role(MagicMock(), SimpleNamespace(id=uuid.uuid4()), code="政策", name="x")


def test_role_code_is_optional_but_description_is_bounded() -> None:
    assert RoleCreateRequest(name="码表管理员").code is None
    with pytest.raises(ValueError):
        RoleCreateRequest(name="x", description="长" * 501)


@pytest.mark.asyncio
async def test_copy_role_copies_grants_but_never_system_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _role("超级管理员", code="superadmin")
    new_id = uuid.uuid4()

    def resource(code: str, published: bool = True, node_type: str = "resource") -> SimpleNamespace:
        return SimpleNamespace(code=code, published=published, node_type=node_type)

    monkeypatch.setattr(role_admin.role_repo, "get_role_by_id", AsyncMock(return_value=source))
    monkeypatch.setattr(
        role_admin.role_repo,
        "list_role_grants",
        AsyncMock(
            return_value=[
                (SimpleNamespace(level="FULL"), resource("policy.sources")),
                (SimpleNamespace(level="READ"), resource("codebook.scenarios")),
                (SimpleNamespace(level="FULL"), resource("system.permissions")),
                (SimpleNamespace(level="FULL"), resource("customer", published=False)),
            ]
        ),
    )
    monkeypatch.setattr(role_admin, "create_role", AsyncMock(return_value={"id": str(new_id), "version": 1}))
    replace = AsyncMock()
    monkeypatch.setattr(role_admin, "replace_grants", replace)
    monkeypatch.setattr(role_admin, "get_role", AsyncMock(return_value={"id": str(new_id)}))

    await role_admin.copy_role(MagicMock(), SimpleNamespace(id=uuid.uuid4()), source.id, name="副本")

    grants = replace.await_args.kwargs["grants"]
    assert grants == [("policy.sources", "FULL"), ("codebook.scenarios", "READ")]


@pytest.mark.asyncio
async def test_effective_permissions_takes_highest_active_role_and_lists_disabled_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=uuid.uuid4(), status="active")
    reader, manager, disabled = _role("只读"), _role("信源配置员"), _role("停用角色", status="disabled")
    monkeypatch.setattr(user_admin.user_repo, "get_user_by_id", AsyncMock(return_value=user))
    monkeypatch.setattr(
        user_admin.user_repo,
        "list_user_grant_sources",
        AsyncMock(
            return_value=[
                ("policy.sources", "READ", reader),
                ("policy.sources", "FULL", manager),
                ("codebook.scenarios", "FULL", disabled),
            ]
        ),
    )
    monkeypatch.setattr(user_admin.resource_repo, "list_all_resources", AsyncMock(return_value=[]))
    result = await user_admin.effective_permissions(MagicMock(), user.id)
    by_code = {item["resource_code"]: item for item in result["items"]}  # type: ignore[union-attr]
    assert by_code["policy.sources"]["level"] == "FULL"
    # 只有停用角色给了权限：列出来源但最终是无权限，页面据此提示「角色已停用」。
    assert by_code["codebook.scenarios"]["level"] == "NONE"
    assert by_code["codebook.scenarios"]["sources"][0]["active"] is False


@pytest.mark.asyncio
async def test_add_members_skips_users_who_already_have_the_role(monkeypatch: pytest.MonkeyPatch) -> None:
    role_id = uuid.uuid4()
    has_it, lacks_it = SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4())
    users = {has_it.id: has_it, lacks_it.id: lacks_it}
    current = {has_it.id: [role_id], lacks_it.id: [uuid.uuid4()]}
    monkeypatch.setattr(user_admin.user_repo, "get_user_for_update", AsyncMock(side_effect=lambda _s, uid: users[uid]))
    monkeypatch.setattr(user_admin.user_repo, "list_user_role_ids", AsyncMock(side_effect=lambda _s, uid: current[uid]))
    set_roles = AsyncMock()
    monkeypatch.setattr(user_admin, "_set_roles", set_roles)

    added = await user_admin.add_role_members(MagicMock(), SimpleNamespace(), role_id, [has_it.id, lacks_it.id])

    assert added == 1
    assert set_roles.await_count == 1
    assert set_roles.await_args.args[3] == [*current[lacks_it.id], role_id]


@pytest.mark.asyncio
async def test_remove_member_keeps_other_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    role_id, other = uuid.uuid4(), uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr(user_admin.user_repo, "get_user_for_update", AsyncMock(return_value=user))
    monkeypatch.setattr(user_admin.user_repo, "list_user_role_ids", AsyncMock(return_value=[role_id, other]))
    set_roles = AsyncMock()
    monkeypatch.setattr(user_admin, "_set_roles", set_roles)
    await user_admin.remove_role_member(MagicMock(), SimpleNamespace(), role_id, user.id)
    assert set_roles.await_args.args[3] == [other]


def test_user_create_accepts_roles_and_defaults_to_none() -> None:
    assert UserCreateRequest(username="zhangsan", display_name="张三").role_ids == []


def _route(path: str, method: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route
    raise AssertionError(f"未找到 {method} {path}")


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/v1/system/roles/{role_id}/members", "POST"),
        ("/api/v1/system/roles/{role_id}/members/{user_id}", "DELETE"),
    ],
)
def test_member_changes_require_grant_permission(path: str, method: str) -> None:
    """从角色一侧增删成员等同于分配角色，门槛必须与「分配角色」一致，不能降成角色管理权限。"""

    marks = [getattr(dep.call, "__authz_permission__", None) for dep in _route(path, method).dependant.dependencies]
    assert ("system.permissions", "grant") in marks


@pytest.mark.asyncio
async def test_builtin_superadmin_grants_are_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """删掉超管的「权限分配」后就再没人能分配角色，后端要和页面一样拒绝修改。"""

    from platform_common.errors import PermissionDeniedError

    from app.domain.catalog import SUPERADMIN_ROLE_CODE

    superadmin = _role("超级管理员", code=SUPERADMIN_ROLE_CODE)
    superadmin.is_builtin = True
    monkeypatch.setattr(role_admin.role_repo, "get_role_for_update", AsyncMock(return_value=superadmin))
    replace = AsyncMock()
    monkeypatch.setattr(role_admin.role_repo, "replace_role_grants", replace)
    with pytest.raises(PermissionDeniedError, match="不能修改授权"):
        await role_admin.replace_grants(
            MagicMock(), SimpleNamespace(id=uuid.uuid4()), superadmin.id, version=1, grants=[]
        )
    replace.assert_not_awaited()
