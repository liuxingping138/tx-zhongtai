"""账号字段的规范化与建人、改人的入参。页面建人和 Excel 批量建人共用同一套校验。"""

from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass, field

from platform_common.errors import ApiError

from app.application.auth_service import normalize_username

USERNAME_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789._-")
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 64

_PHONE_SEPARATORS = re.compile(r"[\s-]")
_MOBILE = re.compile(r"1\d{10}")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


@dataclass(frozen=True, slots=True)
class NewUser:
    username: str
    display_name: str
    phone: str = ""
    email: str = ""
    # 建账号时一并分配的角色；是否有权分配由调用方先校验。
    role_ids: list[uuid.UUID] = field(default_factory=list)
    # 不给口令时生成临时口令。批量导入在线程池里先算好哈希放进 password_hash，跳过现算。
    password: str | None = None
    password_hash: str | None = None


@dataclass(frozen=True, slots=True)
class UserChanges:
    """改人的字段。None 表示不改；电话、邮箱传空串表示清空。"""

    version: int
    display_name: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str | None = None


def validate_username(username: str) -> str:
    normalized = normalize_username(username)
    if not USERNAME_MIN_LENGTH <= len(normalized) <= USERNAME_MAX_LENGTH:
        raise ApiError(f"用户名长度须为 {USERNAME_MIN_LENGTH}-{USERNAME_MAX_LENGTH} 个字符")
    if normalized[0] not in set("abcdefghijklmnopqrstuvwxyz"):
        raise ApiError("用户名须以字母开头")
    if any(ch not in USERNAME_CHARS for ch in normalized):
        raise ApiError("用户名仅允许字母、数字、点、下划线和连字符")
    return normalized


def validate_display_name(display_name: str) -> str:
    display = display_name.strip()
    if not display:
        raise ApiError("显示名不能为空")
    return display


def normalize_phone(phone: str) -> str:
    """去掉空格和连字符后须为 11 位手机号；空串表示没填。"""

    digits = _PHONE_SEPARATORS.sub("", phone)
    if digits and not _MOBILE.fullmatch(digits):
        raise ApiError("电话须为 11 位手机号")
    return digits


def normalize_email(email: str) -> str:
    value = email.strip()
    if value and not _EMAIL.fullmatch(value):
        raise ApiError("邮箱格式不正确")
    return value


def generate_temporary_password() -> str:
    return secrets.token_urlsafe(18)
