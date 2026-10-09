"""用户的 Excel 导出与批量建账号。

导入只新增、不覆盖：用户名已存在的行跳过，避免一份填错的表把别人的角色改掉。
初始密码只出现在这次返回的结果文件里，库里只有哈希。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from io import BytesIO

from anyio import to_thread
from openpyxl import Workbook
from platform_common.clock import format_beijing
from platform_common.errors import ApiError, ErrorCode
from platform_common.excel import SKIP_REASON_COLUMN, append_text_row, parse_sheet_async
from platform_common.filters import FilterValue
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import user_admin
from app.core.config import get_settings
from app.domain.enums import RoleStatus
from app.domain.fields import STATUS_TEXT, USER_EXPORT_COLUMNS, USER_IMPORT_COLUMNS
from app.domain.models import Role, User
from app.domain.password import hash_password
from app.repositories import roles as role_repo
from app.repositories import users as user_repo

ROLE_SEPARATORS = re.compile(r"[、,，;；\n]")
ROLES_IGNORED_NOTE = "角色列已忽略：分配角色需要超级管理员，已放进「待分配角色」"


async def export_users(
    session: AsyncSession,
    *,
    username: FilterValue,
    status: FilterValue,
    role_id: FilterValue,
    keyword: FilterValue,
) -> bytes:
    """按列表同一套筛选导出，所见即所导。不含任何密码相关字段。"""

    filters = {"username": username, "status": status, "role_id": role_id, "keyword": keyword}
    total = await user_repo.count_users(session, **filters)
    limit = get_settings().export_max_rows
    if total > limit:
        raise ApiError(
            f"导出结果 {total} 行，超过单次上限 {limit} 行，请先缩小筛选范围",
            code=ErrorCode.VALIDATION_ERROR,
            http_status=422,
        )
    users = await user_repo.list_users(session, **filters, offset=0, limit=max(total, 1), sort="username")
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
    sheet = book.active
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


async def import_users(session: AsyncSession, actor: User, content: bytes, *, can_grant: bool) -> ImportOutcome:
    settings = get_settings()
    rows = await parse_sheet_async(
        content, USER_IMPORT_COLUMNS, subject="用户", max_rows=settings.user_import_max_rows
    )
    if not rows:
        raise ApiError("Excel 里没有数据", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    index = _role_index(await role_repo.list_all_roles(session)) if can_grant else {}
    outcome = ImportOutcome()
    seen: set[str] = set()

    def skip(row: dict[str, str], reason: str) -> None:
        outcome.skipped.append({**row, SKIP_REASON_COLUMN.field: reason})

    for row in rows:
        try:
            username = user_admin.validate_username(row["username"])
            if not row["display_name"].strip():
                raise ApiError("显示名不能为空")
            phone = user_admin.normalize_phone(row["phone"])
            email = user_admin.normalize_email(row["email"])
        except ApiError as exc:
            skip(row, exc.message)
            continue
        if username in seen:
            skip(row, "文件里有重复的用户名，只建第一行")
            continue
        seen.add(username)
        if await user_repo.get_user_by_username(session, username) is not None:
            skip(row, "用户名已存在，未改动原账号")
            continue
        role_ids: list[uuid.UUID] = []
        note = ""
        if row["roles"].strip():
            if can_grant:
                role_ids, error = _resolve_roles(row["roles"], index)
                if error:
                    skip(row, error)
                    continue
            else:
                note = ROLES_IGNORED_NOTE
        temporary = user_admin.generate_temporary_password()
        # Argon2 一次几十毫秒，几百行在协程里算会把整个服务卡住，放线程池。
        hashed = await to_thread.run_sync(hash_password, temporary)
        payload, _ = await user_admin.create_user(
            session,
            actor,
            username=username,
            display_name=row["display_name"],
            password=None,
            role_ids=role_ids,
            phone=phone,
            email=email,
            password_hash=hashed,
        )
        roles = payload.get("roles") or []
        outcome.created.append(
            {
                "username": username,
                "display_name": row["display_name"].strip(),
                "roles": "、".join(str(role["name"]) for role in roles) if isinstance(roles, list) else "",
                "password": temporary,
                "note": note or ("" if role_ids else "还没有角色，已放进「待分配角色」"),
            }
        )
    return outcome


RESULT_CREATED_HEADERS = ("用户名", "显示名", "角色", "初始密码", "备注")


async def build_import_result(outcome: ImportOutcome) -> bytes:
    return await to_thread.run_sync(_build_import_result, outcome)


def _build_import_result(outcome: ImportOutcome) -> bytes:
    book = Workbook()
    created = book.active
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
