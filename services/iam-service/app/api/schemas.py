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
    token_type: str = "Bearer"
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
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateRequest(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    status: Literal["active", "disabled", "archived"] | None = None
    version: int = Field(ge=1)


class UserRolesReplaceRequest(StrictModel):
    role_ids: list[uuid.UUID]
    version: int = Field(ge=1)


class RoleCreateRequest(StrictModel):
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=128)


class RoleUpdateRequest(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    status: Literal["active", "disabled"] | None = None
    version: int = Field(ge=1)


class GrantItem(StrictModel):
    resource_code: str = Field(min_length=1, max_length=128)
    level: Literal["NONE", "READ", "FULL"]


class RoleGrantsReplaceRequest(StrictModel):
    version: int = Field(ge=1)
    grants: list[GrantItem]


class AuthorizeRequest(StrictModel):
    access_token: str = Field(min_length=1)
    resource: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=64)
