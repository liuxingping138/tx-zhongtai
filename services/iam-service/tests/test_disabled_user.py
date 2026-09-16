from __future__ import annotations

from types import SimpleNamespace

import pytest
from platform_common.errors import UnauthenticatedError

from app.application import auth_service as auth_module
from app.application.auth_service import AuthService
from app.domain.enums import UserStatus
from app.domain.password import hash_password


@pytest.mark.asyncio
async def test_disabled_account_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    user = SimpleNamespace(
        username="locked",
        password_hash=hash_password("correct-horse-1"),
        status=UserStatus.DISABLED,
    )

    async def fake_get(_session: object, _username: str) -> object:
        return user

    monkeypatch.setattr(auth_module.user_repo, "get_user_by_username", fake_get)
    service = AuthService(session=SimpleNamespace(), settings=SimpleNamespace())
    with pytest.raises(UnauthenticatedError, match="账号不可用"):
        await service.authenticate_password("locked", "correct-horse-1")
