"""角色与授权用例。"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from platform_common.clock import utcnow
from platform_common.errors import ApiError, NotFoundError, PermissionDeniedError, VersionConflictError
from platform_common.filters import FilterValue
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.audit_outbox import enqueue_independent
from app.domain.authorization import SYSTEM_PERMISSIONS_CODE
from app.domain.catalog import SUPERADMIN_ROLE_CODE
from app.domain.enums import GrantLevel, NodeType, RoleStatus
from app.domain.models import Role, User
from app.repositories import outbox as outbox_repo
from app.repositories import resources as resource_repo
from app.repositories import roles as role_repo

ROLE_CODE_RE = re.compile(r"^[a-z][a-z0-9._-]{1,63}$")
ROLE_DESCRIPTION_MAX_LENGTH = 500


def role_public(role: Role) -> dict[str, object]:
    return {
        "id": str(role.id),
        "code": role.code,
        "name": role.name,
        "description": role.description or "",
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
    name: FilterValue = None,
) -> tuple[list[dict[str, object]], int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    total = await role_repo.count_roles(session, status=status, name=name)
    rows = await role_repo.list_roles(session, status=status, name=name, offset=(page - 1) * page_size, limit=page_size)
    return await _with_stats(session, rows), total


async def _with_stats(session: AsyncSession, roles: list[Role]) -> list[dict[str, object]]:
    """附上成员数与授权摘要，角色列表据此回答「这个角色能干什么、有几个人在用」。"""

    ids = [role.id for role in roles]
    members = await role_repo.member_counts(session, ids)
    grants = await role_repo.grant_level_counts(session, ids)
    out: list[dict[str, object]] = []
    for role in roles:
        payload = role_public(role)
        counts = grants.get(role.id, {})
        payload["member_count"] = members.get(role.id, 0)
        payload["grant_counts"] = {
            "read": counts.get("READ", 0),
            "export": counts.get("EXPORT", 0),
            "full": counts.get("FULL", 0),
        }
        out.append(payload)
    return out


async def get_role(session: AsyncSession, role_id: uuid.UUID) -> dict[str, object]:
    role = await role_repo.get_role_by_id(session, role_id)
    if role is None:
        raise NotFoundError("角色不存在")
    return (await _with_stats(session, [role]))[0]


async def list_members(session: AsyncSession, role_id: uuid.UUID) -> list[dict[str, object]]:
    role = await role_repo.get_role_by_id(session, role_id)
    if role is None:
        raise NotFoundError("角色不存在")
    return [
        {"id": str(user.id), "username": user.username, "display_name": user.display_name, "status": user.status}
        for user in await role_repo.list_role_members(session, role.id)
    ]


def _clean_description(description: str | None) -> str:
    text = (description or "").strip()
    if len(text) > ROLE_DESCRIPTION_MAX_LENGTH:
        raise ApiError(f"角色说明不能超过 {ROLE_DESCRIPTION_MAX_LENGTH} 字")
    return text


async def create_role(
    session: AsyncSession,
    actor: User,
    *,
    code: str | None,
    name: str,
    description: str | None = None,
) -> dict[str, object]:
    # 编码只作系统内部标识，管理员不必想英文名：不填就自动生成，填了仍按原规则校验。
    normalized = (code or "").strip().lower() or f"role-{uuid.uuid4().hex[:8]}"
    if not ROLE_CODE_RE.match(normalized):
        raise ApiError("角色编码只能用小写字母开头，包含小写字母、数字、点、下划线或短横线")
    display = name.strip()
    if not display:
        raise ApiError("角色名称不能为空")
    now = utcnow()
    role = Role(
        id=uuid.uuid4(),
        code=normalized,
        name=display,
        description=_clean_description(description),
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


@dataclass(frozen=True, slots=True)
class RoleChanges:
    """改角色的字段。None 表示不改。"""

    version: int
    name: str | None = None
    description: str | None = None
    status: str | None = None


async def update_role(
    session: AsyncSession, actor: User, role_id: uuid.UUID, changes: RoleChanges, *, can_grant: bool = False
) -> dict[str, object]:
    """can_grant：操作人有没有「权限分配」（只有超管有）。启用一个停用的角色等于把它的授权还给全部成员，
    和给人分配角色是一回事，只有角色管理权的用户管理员不能做。"""

    role = await role_repo.get_role_for_update(session, role_id)
    if role is None:
        raise NotFoundError("角色不存在")
    if role.version != changes.version:
        raise VersionConflictError()
    status = changes.status
    if role.is_builtin and status is not None and status != role.status:
        raise PermissionDeniedError("不能停用或修改内置角色状态")
    if status is not None:
        if status not in {RoleStatus.ACTIVE, RoleStatus.DISABLED}:
            raise ApiError("无效的角色状态")
        if status == RoleStatus.ACTIVE and role.status != RoleStatus.ACTIVE and not can_grant:
            raise PermissionDeniedError("启用角色会恢复它全部成员的授权，需要「权限分配」权限（超级管理员）")
        role.status = status
    if changes.name is not None:
        display = changes.name.strip()
        if not display:
            raise ApiError("角色名称不能为空")
        role.name = display
    if changes.description is not None:
        role.description = _clean_description(changes.description)
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


async def _normalize_grants(
    session: AsyncSession,
    actor: User,
    role: Role,
    grants: list[tuple[str, str]],
) -> tuple[list[tuple[uuid.UUID, str]], dict[str, tuple[str, str]]]:
    codes = [code for code, level in grants if level != "NONE"]
    if len(set(codes)) != len(codes):
        raise ApiError("同一个模块出现了两次，请刷新后重新选择")
    after: dict[str, tuple[str, str]] = {}
    normalized: list[tuple[uuid.UUID, str]] = []
    for resource_code, level in grants:
        if level == "NONE":
            continue
        if level not in {GrantLevel.READ, GrantLevel.EXPORT, GrantLevel.FULL}:
            raise ApiError("授权等级无效")
        resource = await resource_repo.get_resource_by_code(session, resource_code)
        if resource is None:
            raise PermissionDeniedError("未知资源不可授权")
        if not resource.published or resource.node_type != NodeType.RESOURCE:
            await enqueue_independent(
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
        after[resource.code] = (resource.name, str(level))
    return normalized, after


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
    if role.is_builtin and role.code == SUPERADMIN_ROLE_CODE:
        # 超级管理员固定拥有全部模块的全部功能，由 make seed 维护，页面上也是只读。
        # 放开修改的话，删掉它的「权限分配」后就再没人能给别人分配角色。
        raise PermissionDeniedError("超级管理员角色固定拥有全部权限，不能修改授权")

    before = {
        resource.code: (resource.name, str(grant.level))
        for grant, resource in await role_repo.list_role_grants(session, role.id)
    }
    normalized, after = await _normalize_grants(session, actor, role, grants)

    await role_repo.replace_role_grants(session, role.id, normalized, updated_by=actor.id)
    role.updated_at = utcnow()
    role.version += 1
    await outbox_repo.enqueue(
        session,
        event_type="iam.role.grants_replaced",
        payload={
            "actor_id": str(actor.id),
            "role_id": str(role.id),
            "role_name": role.name,
            "grant_count": len(normalized),
            # 追查「谁开了哪个模块哪一档」：只记变了的模块，原来只有一个数，看不出改了什么。
            "grant_changes": grant_changes(before, after),
            "outcome": "success",
        },
    )
    return await list_grants(session, role.id)


def grant_changes(before: dict[str, tuple[str, str]], after: dict[str, tuple[str, str]]) -> list[dict[str, str]]:
    """{模块编码: (模块名, 档位)} 前后对比，只列变了的；没有授权记作 NONE。"""

    changes = []
    for code in sorted(before.keys() | after.keys()):
        old, new = before.get(code), after.get(code)
        if (old and old[1]) != (new and new[1]):
            name = (new or old or (code, ""))[0]
            changes.append(
                {"module": name, "code": code, "from": old[1] if old else "NONE", "to": new[1] if new else "NONE"}
            )
    return changes


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


async def copy_role(
    session: AsyncSession, actor: User, source_id: uuid.UUID, *, name: str, description: str | None = None
) -> dict[str, object]:
    """以现有角色为模板新建：复制全部模块授权，不复制成员。

    「权限分配」只能属于超级管理员，复制出的新角色不带它。
    """

    source = await role_repo.get_role_by_id(session, source_id)
    if source is None:
        raise NotFoundError("角色不存在")
    created = await create_role(session, actor, code=None, name=name, description=description)
    grants = [
        (resource.code, grant.level)
        for grant, resource in await role_repo.list_role_grants(session, source.id)
        if resource.published and resource.node_type == NodeType.RESOURCE and resource.code != SYSTEM_PERMISSIONS_CODE
    ]
    if not grants:
        return await get_role(session, uuid.UUID(str(created["id"])))
    await replace_grants(
        session, actor, uuid.UUID(str(created["id"])), version=int(str(created["version"])), grants=grants
    )
    return await get_role(session, uuid.UUID(str(created["id"])))
