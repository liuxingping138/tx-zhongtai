from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.authorization import max_level
from app.domain.enums import NodeType, RoleStatus
from app.domain.models import MenuItem, Resource, ResourceAction, Role, RoleGrant, UserGrant, UserRole


async def get_resource_by_code(session: AsyncSession, code: str) -> Resource | None:
    result = await session.execute(select(Resource).where(Resource.code == code))
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

    return (await list_effective_levels_for_users(session, [user_id])).get(user_id, {})


async def list_effective_levels_for_users(
    session: AsyncSession, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, str]]:
    """一批人各自的生效授权（口径同 list_effective_levels，一次查询）：用户列表每行判断能不能管，不逐人查。"""

    if not user_ids:
        return {}
    stmt = (
        select(UserRole.user_id, Resource.code, RoleGrant.level)
        .join(RoleGrant, RoleGrant.resource_id == Resource.id)
        .join(Role, Role.id == RoleGrant.role_id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id.in_(user_ids),
            Role.status == RoleStatus.ACTIVE,
            Resource.published.is_(True),
            Resource.node_type == NodeType.RESOURCE,
        )
    )
    # 角色之外单独给这个人的授权，和角色一起按模块取最高一档。
    direct = (
        select(UserGrant.user_id, Resource.code, UserGrant.level)
        .join(UserGrant, UserGrant.resource_id == Resource.id)
        .where(
            UserGrant.user_id.in_(user_ids),
            Resource.published.is_(True),
            Resource.node_type == NodeType.RESOURCE,
        )
    )
    result = await session.execute(stmt.union_all(direct))
    grouped: dict[uuid.UUID, dict[str, list[str]]] = {}
    for user_id, code, level in result.all():
        grouped.setdefault(user_id, {}).setdefault(code, []).append(level)
    return {
        user_id: {code: chosen for code, levels in by_code.items() if (chosen := max_level(levels))}
        for user_id, by_code in grouped.items()
    }


async def list_effective_levels_by_prefixes(
    session: AsyncSession,
    user_id: uuid.UUID,
    prefixes: list[str],
) -> dict[str, str]:
    """按编码前缀一次查询用户在多个数据范围维度上的生效授权档位。"""

    cleaned = [p.strip() for p in prefixes if p.strip()]
    if not cleaned:
        return {}
    prefix_filter = or_(*(Resource.code.startswith(p) for p in cleaned))
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
            prefix_filter,
        )
    )
    direct = (
        select(Resource.code, UserGrant.level)
        .join(UserGrant, UserGrant.resource_id == Resource.id)
        .where(
            UserGrant.user_id == user_id,
            Resource.published.is_(True),
            Resource.node_type == NodeType.RESOURCE,
            prefix_filter,
        )
    )
    result = await session.execute(stmt.union_all(direct))
    grouped: dict[str, list[str]] = {}
    for code, level in result.all():
        grouped.setdefault(code, []).append(level)
    return {code: chosen for code, levels in grouped.items() if (chosen := max_level(levels))}
