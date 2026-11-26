"""用户 Excel 批量建账号：只新增不覆盖，角色列只对能分配角色的人生效，初始密码只在结果文件里。"""

from __future__ import annotations

import uuid
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from openpyxl import Workbook, load_workbook

from app.application import user_excel
from app.domain.enums import RoleStatus
from app.domain.models import User, UserRole

HEADERS = ["用户名", "显示名", "电话", "邮箱", "角色"]
EDITOR = SimpleNamespace(id=uuid.uuid4(), name="政策编辑", status=RoleStatus.ACTIVE)
VIEWER = SimpleNamespace(id=uuid.uuid4(), name="数据查看", status=RoleStatus.ACTIVE)
OLD = SimpleNamespace(id=uuid.uuid4(), name="旧角色", status=RoleStatus.DISABLED)
ACTOR = SimpleNamespace(id=uuid.uuid4(), display_name="超管")


def _xlsx(*rows: list[str]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


class _FakeSession:
    def __init__(self) -> None:
        self.users: list[User] = []
        self.user_roles: list[UserRole] = []
        self.outbox: list[Any] = []
        self.new: set[Any] = set()
        self.dirty: set[Any] = set()
        self.deleted: set[Any] = set()
        self._in_txn = True
        self.commits = 0
        self.flushes = 0

    def in_transaction(self) -> bool:
        return self._in_txn

    async def commit(self) -> None:
        self.commits += 1
        self._in_txn = False

    def add(self, obj: Any) -> None:
        self.outbox.append(obj)

    def add_all(self, objs: list[Any]) -> None:
        for obj in objs:
            if isinstance(obj, User):
                self.users.append(obj)
            elif isinstance(obj, UserRole):
                self.user_roles.append(obj)
            else:
                self.outbox.append(obj)

    async def flush(self) -> None:
        self.flushes += 1


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    session = _FakeSession()
    existing = {"zhangmin"}
    state = SimpleNamespace(
        session=session,
        existing_calls=0,
        role_list_calls=0,
        hash_in_txn=[],
    )

    async def existing_usernames(_session: object, usernames: Any) -> set[str]:
        state.existing_calls += 1
        return {name for name in usernames if name in existing}

    async def list_all_roles(_session: object) -> list[object]:
        state.role_list_calls += 1
        return [EDITOR, VIEWER, OLD]

    async def fake_hash(password: str) -> str:
        state.hash_in_txn.append(session.in_transaction())
        return f"hashed:{password}"

    monkeypatch.setattr(user_excel.user_repo, "existing_usernames", existing_usernames)
    monkeypatch.setattr(user_excel.role_repo, "list_all_roles", list_all_roles)
    monkeypatch.setattr(user_excel, "hash_password_async", fake_hash)
    return state


@pytest.mark.asyncio
async def test_creates_new_users_and_skips_the_rest(env: SimpleNamespace) -> None:
    content = _xlsx(
        ["liuyang", "刘洋", "138 2200 4411", "liuyang@example.com", "政策编辑、数据查看"],
        ["zhangmin", "张敏", "", "", ""],
        ["liuyang", "刘洋二", "", "", ""],
        ["guojing", "郭静", "1371234", "", ""],
        ["linfeng", "林峰", "", "", "运营主管"],
        ["heyu", "何宇", "", "", "旧角色"],
        ["", "无名", "", "", ""],
    )
    outcome = await user_excel.import_users(env.session, ACTOR, content, can_grant=True)

    assert [item["username"] for item in outcome.created] == ["liuyang"]
    assert env.existing_calls == 1
    assert env.role_list_calls == 1
    # 密码哈希前已释放只读事务，不占用连接池事务。
    assert env.hash_in_txn == [False]
    assert env.session.commits == 1
    assert env.session.flushes == 1
    [user] = env.session.users
    assert user.phone == "13822004411"
    # 哈希是外部先算好传进去的，库里不会存明文。
    assert user.password_hash == f"hashed:{outcome.created[0]['password']}"
    assert [ur.role_id for ur in env.session.user_roles] == [EDITOR.id, VIEWER.id]
    assert [ev.event_type for ev in env.session.outbox] == ["iam.user.created", "iam.user.roles_replaced"]
    reasons = {row["username"]: row["skip_reason"] for row in outcome.skipped}
    assert reasons["zhangmin"] == "用户名已存在，未改动原账号"
    assert reasons["liuyang"] == "文件里有重复的用户名，只建第一行"
    assert "11 位手机号" in reasons["guojing"]
    assert "运营主管" in reasons["linfeng"]
    # 停用的角色不能通过导入分配。
    assert "旧角色" in reasons["heyu"]
    assert outcome.total == 7


@pytest.mark.asyncio
async def test_without_grant_the_role_column_is_ignored(env: SimpleNamespace) -> None:
    content = _xlsx(["liuyang", "刘洋", "", "", "政策编辑"], ["xuming", "徐明", "", "", ""])
    outcome = await user_excel.import_users(env.session, ACTOR, content, can_grant=False)

    assert env.role_list_calls == 0
    assert env.existing_calls == 1
    assert env.session.user_roles == []
    assert [u.username for u in env.session.users] == ["liuyang", "xuming"]
    assert outcome.created[0]["note"] == user_excel.ROLES_IGNORED_NOTE
    assert "待分配角色" in outcome.created[1]["note"]


@pytest.mark.asyncio
async def test_result_file_carries_passwords_and_skipped_rows(env: SimpleNamespace) -> None:
    content = _xlsx(["liuyang", "刘洋", "", "", "政策编辑"], ["zhangmin", "张敏", "", "", ""])
    outcome = await user_excel.import_users(env.session, ACTOR, content, can_grant=True)
    book = load_workbook(BytesIO(await user_excel.build_import_result(outcome)))

    passwords = list(book["初始密码"].iter_rows(values_only=True))
    assert passwords[0] == user_excel.RESULT_CREATED_HEADERS
    assert passwords[1][:4] == ("liuyang", "刘洋", "政策编辑", outcome.created[0]["password"])
    skipped = list(book["跳过的行"].iter_rows(values_only=True))
    assert skipped[0][-1] == "校验说明"
    assert skipped[1][0] == "zhangmin"


@pytest.mark.asyncio
async def test_empty_sheet_is_rejected(env: SimpleNamespace) -> None:
    with pytest.raises(user_excel.ApiError, match="没有数据"):
        await user_excel.import_users(env.session, ACTOR, _xlsx(), can_grant=True)


@pytest.mark.asyncio
async def test_overlong_names_and_emails_are_skipped_instead_of_failing_the_whole_file(
    env: SimpleNamespace,
) -> None:
    """页面建人有长度限制、导入没有：超长的撞库报错，整份文件一个账号都建不成。"""

    content = _xlsx(["longname", "长" * 200, "", "", ""], ["zhaoliu", "赵六", "", "", ""])
    outcome = await user_excel.import_users(env.session, ACTOR, content, can_grant=False)
    assert [item["username"] for item in outcome.created] == ["zhaoliu"]
    assert "超过" in outcome.skipped[0]["skip_reason"]
