from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest
from platform_common.config import Environment
from platform_common.errors import UnauthenticatedError

from app.core import jwt_keys
from app.core.config import Settings
from app.core.jwt_keys import build_jwks, ensure_jwt_keys, load_public_key
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


def test_jwt_meta_and_public_key_cached_by_mtime_and_reloaded_on_rotation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    token1 = issue_access_token(user_id=user_id, session_id=session_id, settings=settings)

    meta_reads = 0
    pub_loads = 0
    real_read_text = Path.read_text
    real_load_pub = jwt_keys.serialization.load_pem_public_key

    def counted_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        nonlocal meta_reads
        if self.name == "current.json":
            meta_reads += 1
        return real_read_text(self, *args, **kwargs)

    def counted_load_pub(data: bytes, *args: Any, **kwargs: Any) -> Any:
        nonlocal pub_loads
        pub_loads += 1
        return real_load_pub(data, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counted_read_text)
    monkeypatch.setattr(jwt_keys.serialization, "load_pem_public_key", counted_load_pub)

    # 首次 decode 命中缓存中的 current.json，只解析一次 k1 公钥；后续多次 decode 全部命中缓存。
    assert decode_access_token(token1, settings)["sub"] == str(user_id)
    assert decode_access_token(token1, settings)["sub"] == str(user_id)
    assert decode_access_token(token1, settings)["sub"] == str(user_id)
    assert meta_reads == 0
    assert pub_loads == 1

    # 模拟密钥轮换：写入 k2 密钥对并更新 current.json（推进 mtime_ns），自动重载且新旧 kid 均可验签。
    jwt_keys._write_keypair(tmp_path, "k2")
    current_path = tmp_path / "current.json"
    old_mtime = current_path.stat().st_mtime_ns
    current_path.write_text(json.dumps({"current_kid": "k2", "previous_kid": "k1"}), encoding="utf-8")
    os.utime(current_path, ns=(old_mtime + 1_000_000_000, old_mtime + 1_000_000_000))

    token2 = issue_access_token(user_id=user_id, session_id=session_id, settings=settings)
    assert decode_access_token(token2, settings)["sub"] == str(user_id)
    assert decode_access_token(token1, settings)["sub"] == str(user_id)
    assert meta_reads == 1
    assert pub_loads == 2

    # 替换 k2 公钥文件内容并推进 mtime_ns，load_public_key 自动重载。
    pub_path = tmp_path / "k2.pub"
    old_pub_mtime = pub_path.stat().st_mtime_ns
    os.utime(pub_path, ns=(old_pub_mtime + 1_000_000_000, old_pub_mtime + 1_000_000_000))
    load_public_key(tmp_path, "k2")
    assert pub_loads == 3
