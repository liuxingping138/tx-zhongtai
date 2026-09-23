"""IAM 公共表 ORM 模型。不包含任何业务表。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.orm_base import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "iam_users"
    __table_args__ = {"comment": "用户"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="用户名")
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="显示名")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码哈希")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", comment="状态")
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="必须改密")
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近改密时间"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")

    user_roles: Mapped[list[UserRole]] = relationship(back_populates="user")


class Role(Base):
    __tablename__ = "iam_roles"
    __table_args__ = {"comment": "角色"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="角色编码")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="角色名称")
    # 写给管理员看的职责说明，例如「负责政策三张表的日常维护」，分配角色时据此判断选哪个。
    description: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default="", comment="角色说明"
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", comment="状态")
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否内置")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="版本号")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")


class UserRole(Base):
    __tablename__ = "iam_user_roles"
    # 唯一性由 (user_id, role_id) 复合主键保证，库里就是这一个约束
    # （名字沿用 uq_iam_user_roles_user_role）。不要再额外声明同列的
    # UniqueConstraint，那会让 alembic check 反复提议补一个不存在的约束。
    __table_args__ = {"comment": "用户角色关系"}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam_users.id", ondelete="RESTRICT"), primary_key=True, comment="用户ID"
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam_roles.id", ondelete="RESTRICT"), primary_key=True, comment="角色ID"
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, comment="授权人ID")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="授权时间")

    user: Mapped[User] = relationship(back_populates="user_roles")


class Resource(Base):
    __tablename__ = "iam_resources"
    __table_args__ = {"comment": "资源"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, comment="资源编码")
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam_resources.id", ondelete="RESTRICT"), nullable=True, comment="父资源ID"
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="资源名称")
    service_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="所属服务")
    node_type: Mapped[str] = mapped_column(String(16), nullable=False, comment="节点类型")
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, comment="是否发布")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")


class ResourceAction(Base):
    __tablename__ = "iam_resource_actions"
    __table_args__ = (
        UniqueConstraint("resource_id", "action_code", name="uq_iam_resource_actions_resource_action"),
        {"comment": "资源动作"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam_resources.id", ondelete="RESTRICT"), nullable=False, comment="资源ID"
    )
    action_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="动作编码")
    required_level: Mapped[str] = mapped_column(String(8), nullable=False, comment="所需权限级别")


class RoleGrant(Base):
    __tablename__ = "iam_role_grants"
    # 同 UserRole：唯一性由 (role_id, resource_id) 复合主键保证。
    __table_args__ = {"comment": "角色授权"}

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam_roles.id", ondelete="RESTRICT"), primary_key=True, comment="角色ID"
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam_resources.id", ondelete="RESTRICT"), primary_key=True, comment="资源ID"
    )
    level: Mapped[str] = mapped_column(String(8), nullable=False, comment="授权级别")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, comment="更新人ID")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="更新时间")


class MenuItem(Base):
    __tablename__ = "iam_menu_items"
    __table_args__ = {"comment": "菜单项"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam_menu_items.id", ondelete="RESTRICT"), nullable=True, comment="父菜单ID"
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False, comment="菜单标题")
    route_name: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="路由名称")
    resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam_resources.id", ondelete="RESTRICT"), nullable=True, comment="关联资源ID"
    )
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="图标")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")


class Session(Base):
    __tablename__ = "iam_sessions"
    __table_args__ = {"comment": "登录会话"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("iam_users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="用户ID",
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True, comment="会话族ID")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间")
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True, comment="过期时间"
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="撤销时间")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="最近活跃时间")
    client_info: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True, comment="客户端信息")


class RefreshToken(Base):
    __tablename__ = "iam_refresh_tokens"
    __table_args__ = {"comment": "刷新令牌"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="主键")
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("iam_sessions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="会话ID",
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="令牌哈希")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="签发时间")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="过期时间")
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="消费时间")
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, comment="替换令牌ID")


class OutboxEvent(Base):
    __tablename__ = "iam_outbox"
    __table_args__ = {"comment": "身份服务出站事件"}

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid, comment="事件ID")
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, comment="事件类型")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="事件结构版本")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, comment="事件内容")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True, comment="投递状态")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="重试次数")
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, comment="下次重试时间"
    )
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="租约截止时间")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, comment="创建时间")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因")
