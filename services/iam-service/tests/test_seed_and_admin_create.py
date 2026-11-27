"""目录同步首次建齐、再次执行只更新；初始管理员已存在时不改写密码。"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application import admin_create, seed
from app.application.admin_create import AdminCreateError, create_initial_admin
from app.domain.catalog import ACTION_SPECS, MENU_SPECS, RESOURCE_SPECS, RETIRED_ACTIONS
from app.domain.enums import NodeType, UserStatus
from app.domain.models import MenuItem, Resource, ResourceAction, Role, RoleGrant, User, UserRole

STRONG_PASSWORD = "dev-only-Passw0rd!2026"


class _Result:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _Session:
    """execute 按顺序吐出预设结果；没有预设时用 factory 现造。"""

    def __init__(self, results: list[Any] | None = None, factory: Any = None) -> None:
        self._results = list(results or [])
        self._factory = factory
        self.added: list[Any] = []
        self.scalars = AsyncMock(return_value=[])
        self.flush = AsyncMock()

    async def execute(self, _statement: Any) -> _Result:
        if self._results:
            return _Result(self._results.pop(0))
        return _Result(self._factory() if self._factory else None)

    def add(self, row: Any) -> None:
        self.added.append(row)


def _of(session: _Session, kind: type) -> list[Any]:
    return [row for row in session.added if isinstance(row, kind)]


@pytest.fixture(autouse=True)
def outbox(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    enqueue = AsyncMock()
    monkeypatch.setattr(seed.outbox_repo, "enqueue", enqueue)
    monkeypatch.setattr(admin_create.outbox_repo, "enqueue", enqueue)
    return enqueue


async def test_first_sync_creates_catalog_with_stable_ids(outbox: AsyncMock) -> None:
    session = _Session()
    counts = await seed.sync_catalog(session)  # type: ignore[arg-type]

    assert counts == {"resources": len(RESOURCE_SPECS), "actions": len(ACTION_SPECS), "menus": len(MENU_SPECS)}
    resources = _of(session, Resource)
    assert len(resources) == len(RESOURCE_SPECS)
    assert len(_of(session, ResourceAction)) == len(ACTION_SPECS)
    assert len(_of(session, MenuItem)) == len(MENU_SPECS)
    # 重新部署后资源 ID 不变，否则已有授权会对不上。
    assert resources[0].id == seed._stable_id(f"resource:{RESOURCE_SPECS[0].code}")
    by_code = {row.code: row for row in resources}
    child = next(spec for spec in RESOURCE_SPECS if spec.parent_code)
    assert by_code[child.code].parent_id == by_code[child.parent_code].id
    outbox.assert_awaited_once()


async def test_superadmin_gets_full_grant_on_every_published_leaf() -> None:
    session = _Session()
    await seed.sync_catalog(session)  # type: ignore[arg-type]

    (role,) = _of(session, Role)
    assert role.is_builtin
    leaves = [spec for spec in RESOURCE_SPECS if spec.published and spec.node_type != NodeType.DIRECTORY]
    grants = _of(session, RoleGrant)
    assert len(grants) == len(leaves)
    assert {grant.level for grant in grants} == {"FULL"}


async def test_second_sync_updates_in_place() -> None:
    session = _Session(factory=lambda: MagicMock(id=uuid.uuid4()))
    await seed.sync_catalog(session)  # type: ignore[arg-type]
    assert session.added == []


async def test_sync_renames_existing_knowledge_resource_and_menu_in_place() -> None:
    existing_resources = {
        spec.code: Resource(
            id=seed._stable_id(f"resource:{spec.code}"),
            code=spec.code,
            name="知识库" if spec.code == "thinktank.knowledge" else spec.name,
            service_code=spec.service_code,
            node_type=spec.node_type,
            published=spec.published,
            sort_order=spec.sort_order,
        )
        for spec in RESOURCE_SPECS
    }
    existing_menus = {
        spec.code: MenuItem(
            id=seed._stable_id(f"menu:{spec.code}"),
            title="知识库" if spec.code == "menu.thinktank.knowledge" else spec.title,
            route_name=spec.route_name,
            sort_order=spec.sort_order,
            enabled=spec.enabled,
        )
        for spec in MENU_SPECS
    }
    results = [
        *[None for _ in RETIRED_ACTIONS],
        *[existing_resources[spec.code] for spec in RESOURCE_SPECS],
        *[MagicMock() for _ in ACTION_SPECS],
        *[existing_menus[spec.code] for spec in MENU_SPECS],
    ]
    session = _Session(results=results, factory=lambda: MagicMock(id=uuid.uuid4()))
    await seed.sync_catalog(session)  # type: ignore[arg-type]
    assert existing_resources["thinktank.knowledge"].name == "资料库"
    assert existing_menus["menu.thinktank.knowledge"].title == "资料库"


async def test_admin_create_rejects_bad_input() -> None:
    with pytest.raises(AdminCreateError, match="用户名不能为空"):
        await create_initial_admin(_Session(), username="  ", password=STRONG_PASSWORD)  # type: ignore[arg-type]
    with pytest.raises(AdminCreateError):
        await create_initial_admin(_Session(), username="admin", password="short")  # type: ignore[arg-type]
    with pytest.raises(AdminCreateError, match="make seed"):
        await create_initial_admin(_Session([None]), username="admin", password=STRONG_PASSWORD)  # type: ignore[arg-type]


async def test_admin_create_makes_user_that_must_change_password(outbox: AsyncMock) -> None:
    role = MagicMock(id=uuid.uuid4())
    session = _Session([role, None])
    user, created = await create_initial_admin(session, username=" Admin ", password=STRONG_PASSWORD)  # type: ignore[arg-type]

    assert created
    assert (user.username, user.status, user.must_change_password) == ("admin", UserStatus.ACTIVE, True)
    assert user.password_hash != STRONG_PASSWORD
    (link,) = _of(session, UserRole)
    assert (link.user_id, link.role_id) == (user.id, role.id)
    outbox.assert_awaited_once()


async def test_existing_admin_keeps_password_and_regains_role(outbox: AsyncMock) -> None:
    existing = User(id=uuid.uuid4(), username="admin", password_hash="old-hash")
    session = _Session([MagicMock(id=uuid.uuid4()), existing, None])
    user, created = await create_initial_admin(session, username="admin", password=STRONG_PASSWORD)  # type: ignore[arg-type]

    assert (user, created) == (existing, False)
    assert existing.password_hash == "old-hash"
    assert len(_of(session, UserRole)) == 1
    outbox.assert_not_awaited()
