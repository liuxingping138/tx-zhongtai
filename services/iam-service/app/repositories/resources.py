from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.authorization import max_level
from app.domain.enums import NodeType, RoleStatus
from app.domain.models import MenuItem, Resource, ResourceAction, Role, RoleGrant, UserGrant, UserRole


async def get_resource_by_code(session: AsyncSession, code: str) -> Resource | None:
    result = await session.execute(select(Resource).where(Resource.code == code))
    return result.scalar_one_or_none()


async def get_action(session: AsyncSession, resource_id: uuid.UUID, action_code: str) -> ResourceAction | None:
    result = await session.execute(
        select(ResourceAction).where(
            ResourceAction.resource_id == resource_id,
            ResourceAction.action_code == action_code,
        )
    )
    return result.scalar_one_or_none()


async def list_all_resources(session: AsyncSession) -> list[Resource]:
    result = await session.execute(select(Resource).order_by(Resource.sort_order, Resource.code))
    return list(result.scalars().all())


async def list_all_actions(session: AsyncSession) -> list[ResourceAction]:
    result = await session.execute(select(ResourceAction))
    return list(result.scalars().all())


async def list_all_menus(session: AsyncSession) -> list[MenuItem]:
    result = await session.execute(select(MenuItem).order_by(MenuItem.sort_order))
    return list(result.scalars().all())


async def effective_level(session: AsyncSession, user_id: uuid.UUID, resource_id: uuid.UUID) -> str | None:
    """这个人在一个模块上的最高授权：启用角色加单独授权，一条查询。

    鉴权每次都调，只查这一个模块。模块是否已发布、是不是叶子由调用方按资源目录先判断，
    口径与 list_effective_levels 一致。每次现查，撤销角色或授权下一次判定就生效。
    """

    by_role = (
        select(RoleGrant.level)
        .join(Role, Role.id == RoleGrant.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id, Role.status == RoleStatus.ACTIVE, RoleGrant.resource_id == resource_id)
    )
    direct = select(UserGrant.level).where(UserGrant.user_id == user_id, UserGrant.resource_id == resource_id)
    result = await session.execute(by_role.union_all(direct))
    return max_level(level for (level,) in result.all())


async def list_effective_levels(session: AsyncSession, user_id: uuid.UUID) -> dict[str, str]:
    """启用角色加单独授权，在已发布叶子资源上的最高授权。每次判定读取当前权威状态。"""

    stmt = (
        select(Resource.code, RoleGrant.level)
        .join(RoleGrant, RoleGrant.resource_id == Resource.id)
        .join(Role, Role.id == RoleGrant.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            Role.status == RoleStatus.ACTIVE,
            Resource.published.is_(True),
            Resource.node_type == NodeType.RESOURCE,
        )
    )
    # 角色之外单独给这个人的授权，和角色一起按模块取最高一档。
    direct = (
        select(Resource.code, UserGrant.level)
        .join(UserGrant, UserGrant.resource_id == Resource.id)
        .where(
            UserGrant.user_id == user_id,
            Resource.published.is_(True),
            Resource.node_type == NodeType.RESOURCE,
        )
    )
    result = await session.execute(stmt.union_all(direct))
    grouped: dict[str, list[str]] = {}
    for code, level in result.all():
        grouped.setdefault(code, []).append(level)
    merged: dict[str, str] = {}
    for code, levels in grouped.items():
        chosen = max_level(levels)
        if chosen:
            merged[code] = chosen
    return merged
