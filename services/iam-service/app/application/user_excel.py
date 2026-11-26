"""用户的 Excel 导出与批量建账号。

导入只新增、不覆盖：用户名已存在的行跳过，避免一份填错的表把别人的角色改掉。
初始密码只出现在这次返回的结果文件里，库里只有哈希。
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from io import BytesIO

from anyio import to_thread
from openpyxl import Workbook
from platform_common.clock import format_beijing, utcnow
from platform_common.columns import overlong_reasons, string_lengths
from platform_common.errors import ApiError, ErrorCode
from platform_common.excel import SKIP_REASON_COLUMN, active_worksheet, append_text_row, parse_sheet_async
from platform_common.request_context import get_request_id
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.user_fields import (
    NewUser,
    generate_temporary_password,
    normalize_email,
    normalize_phone,
    validate_display_name,
    validate_username,
)
from app.core.config import get_settings
from app.domain.enums import RoleStatus, UserStatus
from app.domain.fields import STATUS_TEXT, USER_EXPORT_COLUMNS, USER_IMPORT_COLUMNS
from app.domain.filters import UserFilters
from app.domain.models import Role, User, UserRole
from app.domain.password import hash_password_async
from app.repositories import outbox as outbox_repo
from app.repositories import roles as role_repo
from app.repositories import users as user_repo

ROLE_SEPARATORS = re.compile(r"[、,，;；\n]")
ROLES_IGNORED_NOTE = "角色列已忽略：分配角色需要超级管理员，已放进「待分配角色」"


async def export_users(session: AsyncSession, filters: UserFilters, *, actor: User | None = None) -> bytes:
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
    if actor is not None:
        await outbox_repo.enqueue(
            session,
            event_type="iam.user.exported",
            payload={
                "actor_id": str(actor.id),
                "actor_name": actor.display_name,
                "request_id": get_request_id(),
                "exported_rows": len(rows),
                "filters": filters.model_dump(exclude_none=True) if hasattr(filters, "model_dump") else {},
            },
        )
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
class _ValidatedRow:
    username: str
    display_name: str
    phone: str
    email: str
    raw_roles: str


@dataclass(frozen=True, slots=True)
class _ImportRow:
    user: NewUser
    note: str


async def _release_read_txn(session: AsyncSession) -> None:
    """密码哈希耗 CPU（百行需数十秒），释放只读事务归还连接池，避免触发 idle_in_transaction 超时。"""

    in_txn = getattr(session, "in_transaction", None)
    if callable(in_txn) and in_txn() and not (session.new or session.dirty or session.deleted):
        await session.commit()


async def import_users(session: AsyncSession, actor: User, content: bytes, *, can_grant: bool) -> ImportOutcome:
    settings = get_settings()
    rows = await parse_sheet_async(content, USER_IMPORT_COLUMNS, subject="用户", max_rows=settings.user_import_max_rows)
    if not rows:
        raise ApiError("Excel 里没有数据", code=ErrorCode.VALIDATION_ERROR, http_status=422)
    # 1. 纯内存字段校验与表内去重。
    seen: set[str] = set()
    validated = [(row, _validate_row(row, seen)) for row in rows]
    candidate_usernames = [item.username for _, item in validated if isinstance(item, _ValidatedRow)]

    # 2. 批量查重用户名 + 一次拉取启用角色（不能分配角色时不查角色表）。
    all_roles = await role_repo.list_all_roles(session) if can_grant else []
    index = _role_index(all_roles) if can_grant else None
    roles_by_id = {role.id: role for role in all_roles if role.status == RoleStatus.ACTIVE}
    taken = await user_repo.existing_usernames(session, candidate_usernames) if candidate_usernames else set()

    outcome = ImportOutcome()
    ready: list[_ImportRow] = []
    for row, item in validated:
        if isinstance(item, str):
            outcome.skipped.append({**row, SKIP_REASON_COLUMN.field: item})
            continue
        prepared = _resolve_row(item, taken=taken, index=index)
        if isinstance(prepared, str):
            outcome.skipped.append({**row, SKIP_REASON_COLUMN.field: prepared})
        else:
            ready.append(prepared)

    if not ready:
        return outcome

    # 3. 先释放只读事务，再在受限线程池中并发预计算 Argon2id 哈希，写事务只做极短批量入库。
    await _release_read_txn(session)
    temporaries = [generate_temporary_password() for _ in ready]
    hashes = await asyncio.gather(*(hash_password_async(pwd) for pwd in temporaries))
    outcome.created = await _persist_imported(session, actor, ready, temporaries, hashes, roles_by_id)
    return outcome


USER_LENGTHS = string_lengths(User)


def _validate_row(row: dict[str, str], seen: set[str]) -> _ValidatedRow | str:
    """纯内存校验一行字段格式、长度与表内重复用户名。"""

    try:
        username = validate_username(row["username"])
        display_name = validate_display_name(row["display_name"])
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
    return _ValidatedRow(
        username=username,
        display_name=display_name,
        phone=phone,
        email=email,
        raw_roles=row["roles"],
    )


def _resolve_row(item: _ValidatedRow, *, taken: set[str], index: dict[str, list[Role]] | None) -> _ImportRow | str:
    if item.username in taken:
        return "用户名已存在，未改动原账号"
    role_ids: list[uuid.UUID] = []
    note = ""
    if item.raw_roles.strip():
        if index is None:
            note = ROLES_IGNORED_NOTE
        else:
            role_ids, error = _resolve_roles(item.raw_roles, index)
            if error:
                return error
    user = NewUser(
        username=item.username,
        display_name=item.display_name,
        phone=item.phone,
        email=item.email,
        role_ids=role_ids,
    )
    return _ImportRow(user=user, note=note or ("" if role_ids else "还没有角色，已放进「待分配角色」"))


async def _persist_imported(
    session: AsyncSession,
    actor: User,
    ready: list[_ImportRow],
    temporaries: list[str],
    hashes: list[str],
    roles_by_id: dict[uuid.UUID, Role],
) -> list[dict[str, str]]:
    """一次短事务批量写入用户、用户角色与审计出站事件，避免逐行 flush 与 N×6 角色重复查询。"""

    now = utcnow()
    users: list[User] = []
    user_roles: list[UserRole] = []
    created: list[dict[str, str]] = []
    role_events: list[tuple[User, list[uuid.UUID], list[str]]] = []

    for item, temporary, hashed in zip(ready, temporaries, hashes, strict=True):
        unique_ids = list(dict.fromkeys(item.user.role_ids))
        role_names = [roles_by_id[role_id].name for role_id in unique_ids if role_id in roles_by_id]
        user = User(
            id=uuid.uuid4(),
            username=item.user.username,
            display_name=item.user.display_name,
            phone=item.user.phone,
            email=item.user.email,
            password_hash=hashed,
            status=UserStatus.ACTIVE,
            must_change_password=True,
            version=2 if unique_ids else 1,
            created_at=now,
            updated_at=now,
        )
        users.append(user)
        user_roles.extend(
            UserRole(user_id=user.id, role_id=role_id, granted_by=actor.id, created_at=now) for role_id in unique_ids
        )
        if unique_ids:
            role_events.append((user, unique_ids, role_names))
        created.append(
            {
                "username": user.username,
                "display_name": user.display_name,
                "roles": "、".join(role_names),
                "password": temporary,
                "note": item.note,
            }
        )

    session.add_all(users)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise ApiError("用户名已存在", code=ErrorCode.DUPLICATE, http_status=409) from exc
    if user_roles:
        session.add_all(user_roles)
    for user in users:
        await outbox_repo.enqueue(
            session,
            event_type="iam.user.created",
            payload={
                "actor_id": str(actor.id),
                "target_id": str(user.id),
                "username": user.username,
                "outcome": "success",
            },
        )
    for user, unique_ids, role_names in role_events:
        await outbox_repo.enqueue(
            session,
            event_type="iam.user.roles_replaced",
            payload={
                "actor_id": str(actor.id),
                "target_id": str(user.id),
                "username": user.username,
                "role_ids": [str(item) for item in unique_ids],
                "roles_added": role_names,
                "roles_removed": [],
                "outcome": "success",
            },
        )
    return created


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
