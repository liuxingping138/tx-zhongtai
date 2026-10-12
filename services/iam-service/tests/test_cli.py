"""运维命令：初始密码只从环境变量读，重放只接受已知状态。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.cli import admin_create as admin_cli
from app.cli import outbox_replay as replay_cli


class _Session:
    def __init__(self) -> None:
        self.commit = AsyncMock()

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> _Session:
    fake = _Session()
    monkeypatch.setattr(admin_cli, "SessionLocal", lambda: fake)
    monkeypatch.setattr(replay_cli, "SessionLocal", lambda: fake)
    return fake


async def test_admin_create_refuses_without_password_env(monkeypatch: pytest.MonkeyPatch, session: _Session) -> None:
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert await admin_cli.main() == 2
    session.commit.assert_not_awaited()


async def test_admin_create_commits_and_reports_failure(monkeypatch: pytest.MonkeyPatch, session: _Session) -> None:
    monkeypatch.setenv("ADMIN_PASSWORD", "from-env")
    create = AsyncMock(return_value=(SimpleNamespace(username="admin"), True))
    monkeypatch.setattr(admin_cli, "create_initial_admin", create)
    assert await admin_cli.main() == 0
    assert create.await_args.kwargs["password"] == "from-env"
    session.commit.assert_awaited_once()

    create.side_effect = admin_cli.AdminCreateError("尚未同步内置角色")
    assert await admin_cli.main() == 1


async def test_replay_rejects_unknown_status(monkeypatch: pytest.MonkeyPatch, session: _Session) -> None:
    monkeypatch.setattr("sys.argv", ["outbox_replay", "--status", "delivered"])
    with pytest.raises(SystemExit):
        await replay_cli.main()


async def test_replay_passes_filters_and_commits(monkeypatch: pytest.MonkeyPatch, session: _Session) -> None:
    event_id = uuid.uuid4()
    replay = AsyncMock(return_value=1)
    monkeypatch.setattr(replay_cli.outbox_delivery, "replay", replay)
    monkeypatch.setattr("sys.argv", ["outbox_replay", "--event-id", str(event_id), "--status", "dead"])
    await replay_cli.main()
    kwargs: dict[str, Any] = replay.await_args.kwargs
    assert (kwargs["event_id"], kwargs["statuses"]) == (event_id, ("dead",))
    session.commit.assert_awaited_once()
