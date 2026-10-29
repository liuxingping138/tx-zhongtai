"""用户的 Excel 导出与批量建账号。

导入只新增、不覆盖：用户名已存在的行跳过，避免一份填错的表把别人的角色改掉。
初始密码只出现在这次返回的结果文件里，库里只有哈希。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, replace
from io import BytesIO

from anyio import to_thread
from openpyxl import Workbook
from platform_common.clock import format_beijing
from platform_common.columns import overlong_reasons, string_lengths
from platform_common.errors import ApiError, ErrorCode
from platform_common.excel import SKIP_REASON_COLUMN, active_worksheet, append_text_row, parse_sheet_async
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import user_admin
from app.application.user_fields import (
    NewUser,
    generate_temporary_password,
    normalize_email,
    normalize_phone,
    validate_display_name,
    validate_username,
)
from app.core.config import get_settings
from app.domain.enums import RoleStatus
from app.domain.fields import STATUS_TEXT, USER_EXPORT_COLUMNS, USER_IMPORT_COLUMNS
from app.domain.filters import UserFilters
from app.domain.models import Role, User
from app.domain.password import hash_password
from app.repositories import roles as role_repo
from app.repositories import users as user_repo

ROLE_SEPARATORS = re.compile(r"[、,，;；\n]")
ROLES_IGNORED_NOTE = "角色列已忽略：分配角色需要超级管理员，已放进「待分配角色」"


async def export_users(session: AsyncSession, filters: UserFilters) -> bytes:
    """按列表同一套筛选导出，所见即所导。不含任何密码相关字段。"""

    total = await user_repo.count_users(session, filters)
    limit = get_settings().export_max_rows
    if total > limit:
        raise ApiError(
            f"导出结果 {total} 行，超过单次上限 {limit} 行，请先缩小筛选范围",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )
    users = await user_repo.list_users(session, filters, offset=0, limit=max(total, 1), sort="username")
    roles = await user_repo.roles_for_users(session, [user.id for user in users])
    rows = [
        {
            "username": user.username,
            "display_name": user.display_name,
            "phone": user.phone,
            "email": user.email,
            "roles": "、".join(role.name for role in roles.get(user.id, [])),
            "status": STATUS_TEXT.get(user.status, user.status),
            "created_at": format_beijing(user.created_at),
        }
        for user in users
    ]
    return await to_thread.run_sync(_build_export, rows)


def _build_export(rows: list[dict[str, str]]) -> bytes:
    book = Workbook()
    sheet = active_worksheet(book)
    sheet.title = "用户"
    append_text_row(sheet, [spec.header for spec in USER_EXPORT_COLUMNS])
    for row in rows:
        append_text_row(sheet, [row.get(spec.field, "") for spec in USER_EXPORT_COLUMNS])
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


@dataclass
class ImportOutcome:
    created: list[dict[str, str]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.created) + len(self.skipped)


def _role_index(roles: list[Role]) -> dict[str, list[Role]]:
    index: dict[str, list[Role]] = {}
    for role in roles:
        if role.status == RoleStatus.ACTIVE:
            index.setdefault(role.name.strip(), []).append(role)
    return index


def _resolve_roles(raw: str, index: dict[str, list[Role]]) -> tuple[list[uuid.UUID], str]:
    """按名称找启用中的角色。返回 (角色 id, 错误说明)；有错误时整行跳过。"""

    names = list(dict.fromkeys(name.strip() for name in ROLE_SEPARATORS.split(raw) if name.strip()))
    ids: list[uuid.UUID] = []
    unknown: list[str] = []
    ambiguous: list[str] = []
    for name in names:
        matches = index.get(name, [])
        if not matches:
            unknown.append(name)
        elif len(matches) > 1:
            ambiguous.append(name)
        else:
            ids.append(matches[0].id)
    if unknown:
        return [], f"没有叫「{'、'.join(unknown)}」的启用角色"
    if ambiguous:
        return [], f"有多个角色叫「{'、'.join(ambiguous)}」，请建好账号后在页面上分配"
    return ids, ""


@dataclass(frozen=True, slots=True)
class _ImportRow:
    user: NewUser
    note: str


async def import_users(session: AsyncSession, actor: User, content: bytes, *, can_grant: bool) -> ImportOutcome:
    settings = get_settings()
    rows = await parse_sheet_async(content, USER_IMPORT_COLUMNS, subject="用户", max_rows=settings.user_import_max_rows)
    if not rows:
        raise ApiError("Excel 里没有数据", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    # 不能分配角色时不查角色表：角色列整列忽略，按名称匹配不到也不算错。
    index = _role_index(await role_repo.list_all_roles(session)) if can_grant else None
    outcome = ImportOutcome()
    seen: set[str] = set()
    for row in rows:
        prepared = await _prepare_row(session, row, seen, index)
        if isinstance(prepared, str):
            outcome.skipped.append({**row, SKIP_REASON_COLUMN.field: prepared})
        else:
            outcome.created.append(await _create_imported(session, actor, prepared))
    return outcome


USER_LENGTHS = string_lengths(User)


async def _prepare_row(
    session: AsyncSession, row: dict[str, str], seen: set[str], index: dict[str, list[Role]] | None
) -> _ImportRow | str:
    """校验一行并解析角色。可以建账号时返回入参，否则返回跳过原因。"""

    try:
        username = validate_username(row["username"])
        validate_display_name(row["display_name"])
        phone = normalize_phone(row["phone"])
        email = normalize_email(row["email"])
    except ApiError as exc:
        return exc.message
    # 页面建人有长度限制，导入这条路原来没有：超长的显示名、邮箱撞库报错，整份文件一个账号都建不成。
    if reasons := overlong_reasons(
        {"username": username, "display_name": row["display_name"], "phone": phone, "email": email},
        USER_IMPORT_COLUMNS,
        USER_LENGTHS,
    ):
        return "、".join(reasons)
    if username in seen:
        return "文件里有重复的用户名，只建第一行"
    seen.add(username)
    if await user_repo.get_user_by_username(session, username) is not None:
        return "用户名已存在，未改动原账号"
    role_ids: list[uuid.UUID] = []
    note = ""
    if row["roles"].strip():
        if index is None:
            note = ROLES_IGNORED_NOTE
        else:
            role_ids, error = _resolve_roles(row["roles"], index)
            if error:
                return error
    user = NewUser(username=username, display_name=row["display_name"], phone=phone, email=email, role_ids=role_ids)
    return _ImportRow(user=user, note=note or ("" if role_ids else "还没有角色，已放进「待分配角色」"))


async def _create_imported(session: AsyncSession, actor: User, item: _ImportRow) -> dict[str, str]:
    temporary = generate_temporary_password()
    # Argon2 一次几十毫秒，几百行在协程里算会把整个服务卡住，放线程池。
    hashed = await to_thread.run_sync(hash_password, temporary)
    payload, _ = await user_admin.create_user(session, actor, replace(item.user, password_hash=hashed))
    roles = payload.get("roles") or []
    return {
        "username": item.user.username,
        "display_name": item.user.display_name.strip(),
        "roles": "、".join(str(role["name"]) for role in roles) if isinstance(roles, list) else "",
        "password": temporary,
        "note": item.note,
    }


RESULT_CREATED_HEADERS = ("用户名", "显示名", "角色", "初始密码", "备注")


async def build_import_result(outcome: ImportOutcome) -> bytes:
    return await to_thread.run_sync(_build_import_result, outcome)


def _build_import_result(outcome: ImportOutcome) -> bytes:
    book = Workbook()
    created = active_worksheet(book)
    created.title = "初始密码"
    append_text_row(created, list(RESULT_CREATED_HEADERS))
    for item in outcome.created:
        append_text_row(
            created, [item["username"], item["display_name"], item["roles"], item["password"], item["note"]]
        )
    if outcome.skipped:
        skipped = book.create_sheet("跳过的行")
        columns = (*USER_IMPORT_COLUMNS, SKIP_REASON_COLUMN)
        append_text_row(skipped, [spec.header for spec in columns])
        for row in outcome.skipped:
            append_text_row(skipped, [row.get(spec.field, "") for spec in columns])
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()
