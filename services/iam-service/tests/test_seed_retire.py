"""已下线资源的清理：菜单、授权、动作和资源本身都要删，且重复同步没有副作用。"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from app.application import seed


class _Session:
    def __init__(self, ids: list[uuid.UUID]) -> None:
        self.scalars = AsyncMock(return_value=ids)
        self.execute = AsyncMock()


async def test_retire_removes_dependents_before_the_resource() -> None:
    session = _Session([uuid.uuid4()])
    removed = await seed._retire_resources(session)  # type: ignore[arg-type]

    assert removed == 1
    tables = [call.args[0].table.name for call in session.execute.await_args_list]
    assert tables == ["iam_menu_items", "iam_role_grants", "iam_resource_actions", "iam_resources"]


async def test_retire_is_a_noop_when_already_gone() -> None:
    session = _Session([])
    assert await seed._retire_resources(session) == 0  # type: ignore[arg-type]
    session.execute.assert_not_awaited()
