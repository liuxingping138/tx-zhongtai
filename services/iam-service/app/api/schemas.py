from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class TokenPayload(BaseModel):
    access_token: str
    token_type: str = "Bearer"  # noqa: S105  OAuth 令牌类型名，不是口令
    expires_in: int
    must_change_password: bool


class MePayload(BaseModel):
    id: str
    username: str
    display_name: str
    must_change_password: bool
    status: str
    is_superadmin: bool
    roles: list[str] = []


class CsrfPayload(BaseModel):
    csrf_token: str


class UserCreateRequest(StrictModel):
    username: str = Field(min_length=3, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    phone: str = Field(default="", max_length=32)
    email: str = Field(default="", max_length=254)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    # 建账号时一并分配的角色；非空时要求操作人有「权限分配」可管理。
    role_ids: list[uuid.UUID] = Field(default_factory=list)


class UserUpdateRequest(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    # 不传表示不改；传空串表示清空。
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=254)
    status: Literal["active", "disabled"] | None = None
    version: int = Field(ge=1)


class UserRolesReplaceRequest(StrictModel):
    role_ids: list[uuid.UUID]
    version: int = Field(ge=1)


class RoleCreateRequest(StrictModel):
    # 不填由系统生成，管理员只需要起中文名。
    code: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)


class RoleCopyRequest(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)


class RoleMembersAddRequest(StrictModel):
    user_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class RoleUpdateRequest(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=500)
    status: Literal["active", "disabled"] | None = None
    version: int = Field(ge=1)


class GrantItem(StrictModel):
    resource_code: str = Field(min_length=1, max_length=128)
    level: Literal["NONE", "READ", "EXPORT", "FULL"]


class RoleGrantsReplaceRequest(StrictModel):
    version: int = Field(ge=1)
    grants: list[GrantItem]


class AuthorizeRequest(StrictModel):
    access_token: str = Field(min_length=1)
    resource: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=64)
