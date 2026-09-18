"""幂等同步资源、动作、菜单与内置超级管理员角色。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.domain.catalog import (
    ACTION_SPECS,
    MENU_SPECS,
    RESOURCE_SPECS,
    SUPERADMIN_ROLE_CODE,
    SUPERADMIN_ROLE_NAME,
)
from app.domain.enums import NodeType, RoleStatus
from app.domain.models import MenuItem, Resource, ResourceAction, Role, RoleGrant
from app.repositories import outbox as outbox_repo

_NS = uuid.UUID("8f2c6d1a-3b7e-4d90-9a11-6c4f0e8b2d55")


def _stable_id(code: str) -> uuid.UUID:
    return uuid.uuid5(_NS, code)


async def _upsert_resources(session: AsyncSession) -> dict[str, Resource]:
    by_code: dict[str, Resource] = {}
    for spec in RESOURCE_SPECS:
        result = await session.execute(select(Resource).where(Resource.code == spec.code))
        row = result.scalar_one_or_none()
        parent_id = by_code[spec.parent_code].id if spec.parent_code else None
        if row is None:
            row = Resource(
                id=_stable_id(f"resource:{spec.code}"),
                code=spec.code,
                parent_id=parent_id,
                name=spec.name,
                service_code=spec.service_code,
                node_type=spec.node_type,
                published=spec.published,
                sort_order=spec.sort_order,
            )
            session.add(row)
            await session.flush()
        else:
            row.parent_id = parent_id
            row.name = spec.name
            row.service_code = spec.service_code
            row.node_type = spec.node_type
            row.published = spec.published
            row.sort_order = spec.sort_order
        by_code[spec.code] = row
    return by_code


async def _upsert_actions(session: AsyncSession, resources: dict[str, Resource]) -> None:
    for spec in ACTION_SPECS:
        resource = resources[spec.resource_code]
        result = await session.execute(
            select(ResourceAction).where(
                ResourceAction.resource_id == resource.id,
                ResourceAction.action_code == spec.action_code,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            session.add(
                ResourceAction(
                    resource_id=resource.id,
                    action_code=spec.action_code,
                    required_level=spec.required_level,
                )
            )
        else:
            row.required_level = spec.required_level


async def _upsert_menus(session: AsyncSession, resources: dict[str, Resource]) -> None:
    by_code: dict[str, MenuItem] = {}
    for spec in MENU_SPECS:
        menu_id = _stable_id(f"menu:{spec.code}")
        result = await session.execute(select(MenuItem).where(MenuItem.id == menu_id))
        row = result.scalar_one_or_none()
        parent_id = by_code[spec.parent_code].id if spec.parent_code else None
        resource_id = resources[spec.resource_code].id if spec.resource_code else None
        if row is None:
            row = MenuItem(
                id=menu_id,
                parent_id=parent_id,
                title=spec.title,
                route_name=spec.route_name,
                resource_id=resource_id,
                icon=spec.icon,
                sort_order=spec.sort_order,
                enabled=spec.enabled,
            )
            session.add(row)
            await session.flush()
        else:
            row.parent_id = parent_id
            row.title = spec.title
            row.route_name = spec.route_name
            row.resource_id = resource_id
            row.icon = spec.icon
            row.sort_order = spec.sort_order
            row.enabled = spec.enabled
        by_code[spec.code] = row


async def _ensure_superadmin_role(session: AsyncSession, resources: dict[str, Resource]) -> Role:
    now = utcnow()
    result = await session.execute(select(Role).where(Role.code == SUPERADMIN_ROLE_CODE))
    role = result.scalar_one_or_none()
    if role is None:
        role = Role(
            id=uuid.uuid4(),
            code=SUPERADMIN_ROLE_CODE,
            name=SUPERADMIN_ROLE_NAME,
            status=RoleStatus.ACTIVE,
            is_builtin=True,
            version=1,
            created_at=now,
            updated_at=now,
        )
        session.add(role)
        await session.flush()
    else:
        role.name = SUPERADMIN_ROLE_NAME
        role.is_builtin = True
        role.status = RoleStatus.ACTIVE
        role.updated_at = now

    for spec in RESOURCE_SPECS:
        if not spec.published or spec.node_type == NodeType.DIRECTORY:
            continue
        resource = resources[spec.code]
        grant_result = await session.execute(
            select(RoleGrant).where(RoleGrant.role_id == role.id, RoleGrant.resource_id == resource.id)
        )
        grant = grant_result.scalar_one_or_none()
        if grant is None:
            session.add(
                RoleGrant(
                    role_id=role.id,
                    resource_id=resource.id,
                    level="FULL",
                    updated_at=now,
                )
            )
        else:
            grant.level = "FULL"
            grant.updated_at = now
    return role


async def sync_catalog(session: AsyncSession) -> dict[str, int]:
    resources = await _upsert_resources(session)
    await _upsert_actions(session, resources)
    await _upsert_menus(session, resources)
    await _ensure_superadmin_role(session, resources)
    await outbox_repo.enqueue(
        session,
        event_type="iam.catalog.synced",
        payload={"resource_count": len(RESOURCE_SPECS), "action_count": len(ACTION_SPECS), "outcome": "success"},
    )
    return {
        "resources": len(RESOURCE_SPECS),
        "actions": len(ACTION_SPECS),
        "menus": len(MENU_SPECS),
    }
