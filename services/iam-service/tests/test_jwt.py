from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from platform_common.config import Environment
from platform_common.errors import UnauthenticatedError

from app.core.config import Settings
from app.core.jwt_keys import build_jwks, ensure_jwt_keys
from app.core.jwt_tokens import decode_access_token, issue_access_token


def _settings(keys_dir: Path) -> Settings:
    return Settings(
        environment=Environment.TEST,
        database_url="postgresql+asyncpg://iam_app:test@localhost:5432/iam_db",
        redis_url="redis://localhost:6379/0",
        jwt_keys_dir=str(keys_dir),
    )


def test_issue_and_verify_access_token_without_permissions() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        settings = _settings(Path(tmp))
        user_id = uuid.uuid4()
        session_id = uuid.uuid4()
        token = issue_access_token(user_id=user_id, session_id=session_id, settings=settings)
        claims = decode_access_token(token, settings)
        assert claims["sub"] == str(user_id)
        assert claims["sid"] == str(session_id)
        assert "permissions" not in claims
        assert "roles" not in claims
        jwks = build_jwks(settings.jwt_keys_path, ensure_jwt_keys(settings.jwt_keys_path, allow_generate=True))
        assert jwks["keys"][0]["kid"]
        assert jwks["keys"][0]["alg"] == "RS256"


def test_invalid_token_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        settings = _settings(Path(tmp))
        try:
            decode_access_token("not-a-jwt", settings)
            raise AssertionError("should have failed")
        except UnauthenticatedError:
            pass
