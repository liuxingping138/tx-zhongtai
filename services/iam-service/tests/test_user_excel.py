"""用户 Excel 批量建账号：只新增不覆盖，角色列只对能分配角色的人生效，初始密码只在结果文件里。"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from openpyxl import Workbook, load_workbook

from app.application import user_excel
from app.application.user_fields import NewUser
from app.domain.enums import RoleStatus

HEADERS = ["用户名", "显示名", "电话", "邮箱", "角色"]
EDITOR = SimpleNamespace(id=uuid.uuid4(), name="政策编辑", status=RoleStatus.ACTIVE)
VIEWER = SimpleNamespace(id=uuid.uuid4(), name="数据查看", status=RoleStatus.ACTIVE)
OLD = SimpleNamespace(id=uuid.uuid4(), name="旧角色", status=RoleStatus.DISABLED)


def _xlsx(*rows: list[str]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def created(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    existing = {"zhangmin"}

    async def get_by_username(_session: object, username: str) -> object | None:
        return SimpleNamespace(username=username) if username in existing else None

    async def list_all_roles(_session: object) -> list[object]:
        return [EDITOR, VIEWER, OLD]

    async def create_user(_session: object, _actor: object, data: NewUser) -> tuple[dict[str, object], None]:
        calls.append(asdict(data))
        roles = [{"name": role.name} for role in (EDITOR, VIEWER) if role.id in data.role_ids]
        return {"roles": roles}, None

    async def fake_hash(password: str) -> str:
        return f"hashed:{password}"

    monkeypatch.setattr(user_excel.user_repo, "get_user_by_username", get_by_username)
    monkeypatch.setattr(user_excel.role_repo, "list_all_roles", list_all_roles)
    monkeypatch.setattr(user_excel.user_admin, "create_user", create_user)
    monkeypatch.setattr(user_excel, "hash_password_async", fake_hash)
    return calls


@pytest.mark.asyncio
async def test_creates_new_users_and_skips_the_rest(created: list[dict[str, Any]]) -> None:
    content = _xlsx(
        ["liuyang", "刘洋", "138 2200 4411", "liuyang@example.com", "政策编辑、数据查看"],
        ["zhangmin", "张敏", "", "", ""],
        ["liuyang", "刘洋二", "", "", ""],
        ["guojing", "郭静", "1371234", "", ""],
        ["linfeng", "林峰", "", "", "运营主管"],
        ["heyu", "何宇", "", "", "旧角色"],
        ["", "无名", "", "", ""],
    )
    outcome = await user_excel.import_users(SimpleNamespace(), SimpleNamespace(), content, can_grant=True)

    assert [item["username"] for item in outcome.created] == ["liuyang"]
    assert created[0]["role_ids"] == [EDITOR.id, VIEWER.id]
    assert created[0]["phone"] == "13822004411"
    # 哈希是外部先算好传进去的，库里不会存明文。
    assert created[0]["password_hash"] == f"hashed:{outcome.created[0]['password']}"
    reasons = {row["username"]: row["skip_reason"] for row in outcome.skipped}
    assert reasons["zhangmin"] == "用户名已存在，未改动原账号"
    assert reasons["liuyang"] == "文件里有重复的用户名，只建第一行"
    assert "11 位手机号" in reasons["guojing"]
    assert "运营主管" in reasons["linfeng"]
    # 停用的角色不能通过导入分配。
    assert "旧角色" in reasons["heyu"]
    assert outcome.total == 7


@pytest.mark.asyncio
async def test_without_grant_the_role_column_is_ignored(created: list[dict[str, Any]]) -> None:
    content = _xlsx(["liuyang", "刘洋", "", "", "政策编辑"], ["xuming", "徐明", "", "", ""])
    outcome = await user_excel.import_users(SimpleNamespace(), SimpleNamespace(), content, can_grant=False)

    assert [call["role_ids"] for call in created] == [[], []]
    assert outcome.created[0]["note"] == user_excel.ROLES_IGNORED_NOTE
    assert "待分配角色" in outcome.created[1]["note"]


@pytest.mark.asyncio
async def test_result_file_carries_passwords_and_skipped_rows(created: list[dict[str, Any]]) -> None:
    content = _xlsx(["liuyang", "刘洋", "", "", "政策编辑"], ["zhangmin", "张敏", "", "", ""])
    outcome = await user_excel.import_users(SimpleNamespace(), SimpleNamespace(), content, can_grant=True)
    book = load_workbook(BytesIO(await user_excel.build_import_result(outcome)))

    passwords = list(book["初始密码"].iter_rows(values_only=True))
    assert passwords[0] == user_excel.RESULT_CREATED_HEADERS
    assert passwords[1][:4] == ("liuyang", "刘洋", "政策编辑", outcome.created[0]["password"])
    skipped = list(book["跳过的行"].iter_rows(values_only=True))
    assert skipped[0][-1] == "校验说明"
    assert skipped[1][0] == "zhangmin"


@pytest.mark.asyncio
async def test_empty_sheet_is_rejected(created: list[dict[str, Any]]) -> None:
    with pytest.raises(user_excel.ApiError, match="没有数据"):
        await user_excel.import_users(SimpleNamespace(), SimpleNamespace(), _xlsx(), can_grant=True)


@pytest.mark.asyncio
async def test_overlong_names_and_emails_are_skipped_instead_of_failing_the_whole_file(
    created: list[dict[str, Any]],
) -> None:
    """页面建人有长度限制、导入没有：超长的撞库报错，整份文件一个账号都建不成。"""

    content = _xlsx(["longname", "长" * 200, "", "", ""], ["zhaoliu", "赵六", "", "", ""])
    outcome = await user_excel.import_users(SimpleNamespace(), SimpleNamespace(), content, can_grant=False)
    assert [item["username"] for item in outcome.created] == ["zhaoliu"]
    assert "超过" in outcome.skipped[0]["skip_reason"]
