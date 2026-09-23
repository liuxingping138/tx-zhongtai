"""角色与授权用例。"""

from __future__ import annotations

import re
import uuid

from platform_common.errors import ApiError, NotFoundError, PermissionDeniedError, VersionConflictError
from platform_common.filters import FilterValue
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.domain.authorization import SYSTEM_PERMISSIONS_CODE
from app.domain.catalog import SUPERADMIN_ROLE_CODE
from app.domain.enums import GrantLevel, NodeType, RoleStatus
from app.domain.models import Role, User
from app.repositories import outbox as outbox_repo
from app.repositories import resources as resource_repo
from app.repositories import roles as role_repo

ROLE_CODE_RE = re.compile(r"^[a-z][a-z0-9._-]{1,63}$")


def role_public(role: Role) -> dict[str, object]:
    return {
        "id": str(role.id),
        "code": role.code,
        "name": role.name,
        "status": role.status,
        "is_builtin": role.is_builtin,
        "version": role.version,
        "created_at": role.created_at.isoformat(),
        "updated_at": role.updated_at.isoformat(),
    }


async def list_roles_page(
    session: AsyncSession,
    *,
    status: FilterValue,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, object]], int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    total = await role_repo.count_roles(session, status=status)
    rows = await role_repo.list_roles(session, status=status, offset=(page - 1) * page_size, limit=page_size)
    return [role_public(row) for row in rows], total


async def get_role(session: AsyncSession, role_id: uuid.UUID) -> dict[str, object]:
    role = await role_repo.get_role_by_id(session, role_id)
    if role is None:
        raise NotFoundError("角色不存在")
    return role_public(role)


async def create_role(session: AsyncSession, actor: User, *, code: str, name: str) -> dict[str, object]:
    normalized = code.strip().lower()
    if not ROLE_CODE_RE.match(normalized):
        raise ApiError("角色编码格式无效")
    display = name.strip()
    if not display:
        raise ApiError("角色名称不能为空")
    now = utcnow()
    role = Role(
        id=uuid.uuid4(),
        code=normalized,
        name=display,
        status=RoleStatus.ACTIVE,
        is_builtin=False,
        version=1,
        created_at=now,
        updated_at=now,
    )
    session.add(role)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise VersionConflictError("角色编码已存在") from exc
    await outbox_repo.enqueue(
        session,
        event_type="iam.role.created",
        payload={"actor_id": str(actor.id), "role_id": str(role.id), "code": role.code, "outcome": "success"},
    )
    return role_public(role)


async def update_role(
    session: AsyncSession,
    actor: User,
    role_id: uuid.UUID,
    *,
    name: str | None,
    status: str | None,
    version: int,
) -> dict[str, object]:
    role = await role_repo.get_role_for_update(session, role_id)
    if role is None:
        raise NotFoundError("角色不存在")
    if role.version != version:
        raise VersionConflictError()
    if role.is_builtin:
        if status is not None and status != role.status:
            raise PermissionDeniedError("不能停用或修改内置角色状态")
    if status is not None:
        if status not in {RoleStatus.ACTIVE, RoleStatus.DISABLED}:
            raise ApiError("无效的角色状态")
        role.status = status
    if name is not None:
        display = name.strip()
        if not display:
            raise ApiError("角色名称不能为空")
        role.name = display
    role.updated_at = utcnow()
    role.version += 1
    await outbox_repo.enqueue(
        session,
        event_type="iam.role.updated",
        payload={"actor_id": str(actor.id), "role_id": str(role.id), "status": role.status, "outcome": "success"},
    )
    return role_public(role)


async def list_grants(session: AsyncSession, role_id: uuid.UUID) -> dict[str, object]:
    role = await role_repo.get_role_by_id(session, role_id)
    if role is None:
        raise NotFoundError("角色不存在")
    pairs = await role_repo.list_role_grants(session, role.id)
    return {
        "role": role_public(role),
        "grants": [
            {"resource_code": resource.code, "resource_name": resource.name, "level": grant.level}
            for grant, resource in pairs
        ],
    }


async def replace_grants(
    session: AsyncSession,
    actor: User,
    role_id: uuid.UUID,
    *,
    version: int,
    grants: list[tuple[str, str]],
) -> dict[str, object]:
    role = await role_repo.get_role_for_update(session, role_id)
    if role is None:
        raise NotFoundError("角色不存在")
    if role.version != version:
        raise VersionConflictError()

    normalized: list[tuple[uuid.UUID, str]] = []
    for resource_code, level in grants:
        if level == "NONE":
            continue
        if level not in {GrantLevel.READ, GrantLevel.FULL, "READ", "FULL"}:
            raise ApiError("授权等级无效")
        resource = await resource_repo.get_resource_by_code(session, resource_code)
        if resource is None:
            raise PermissionDeniedError("未知资源不可授权")
        if not resource.published or resource.node_type != NodeType.RESOURCE:
            await outbox_repo.enqueue_independent(
                event_type="iam.role.grant_denied",
                payload={
                    "actor_id": str(actor.id),
                    "role_id": str(role.id),
                    "resource_code": resource_code,
                    "outcome": "denied",
                    "reason": "unpublished_or_directory",
                },
            )
            raise PermissionDeniedError("未发布资源或目录节点不能授权")
        if resource.code == SYSTEM_PERMISSIONS_CODE and role.code != SUPERADMIN_ROLE_CODE:
            raise PermissionDeniedError("系统权限分配仅能授予超级管理员角色")
        normalized.append((resource.id, str(level)))

    await role_repo.replace_role_grants(session, role.id, normalized, updated_by=actor.id)
    role.updated_at = utcnow()
    role.version += 1
    await outbox_repo.enqueue(
        session,
        event_type="iam.role.grants_replaced",
        payload={
            "actor_id": str(actor.id),
            "role_id": str(role.id),
            "grant_count": len(normalized),
            "outcome": "success",
        },
    )
    return await list_grants(session, role.id)


async def resource_tree(session: AsyncSession) -> list[dict[str, object]]:
    resources = await resource_repo.list_all_resources(session)
    actions = await resource_repo.list_all_actions(session)
    actions_by_resource: dict[uuid.UUID, list[dict[str, str]]] = {}
    for action in actions:
        actions_by_resource.setdefault(action.resource_id, []).append(
            {"action_code": action.action_code, "required_level": action.required_level}
        )
    nodes: dict[uuid.UUID, dict[str, object]] = {}
    for item in resources:
        nodes[item.id] = {
            "id": str(item.id),
            "code": item.code,
            "name": item.name,
            "service_code": item.service_code,
            "node_type": item.node_type,
            "published": item.published,
            "sort_order": item.sort_order,
            "parent_id": str(item.parent_id) if item.parent_id else None,
            "actions": sorted(actions_by_resource.get(item.id, []), key=lambda row: row["action_code"]),
            "children": [],
        }
    roots: list[dict[str, object]] = []
    for item in resources:
        node = nodes[item.id]
        parent_id = item.parent_id
        if parent_id and parent_id in nodes:
            children = nodes[parent_id]["children"]
            if isinstance(children, list):
                children.append(node)
        else:
            roots.append(node)
    return roots
