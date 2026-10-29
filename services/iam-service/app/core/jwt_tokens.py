"""Access Token 签发与校验。JWT 只含 sub/sid/iss/aud/iat/exp/jti，不含权限树。"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import jwt
from jwt import InvalidTokenError
from platform_common.clock import utcnow
from platform_common.errors import UnauthenticatedError

from app.core.config import Settings
from app.core.jwt_keys import ensure_jwt_keys, load_private_key, load_public_pem


def issue_access_token(*, user_id: uuid.UUID, session_id: uuid.UUID, settings: Settings) -> str:
    meta = ensure_jwt_keys(settings.jwt_keys_path, allow_generate=settings.allow_generate_jwt_keys)
    kid = meta["current_kid"]
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.access_token_ttl_seconds)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(
        payload,
        load_private_key(settings.jwt_keys_path, kid),
        algorithm=settings.jwt_algorithm,
        headers={"kid": kid},
    )


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    if not token:
        raise UnauthenticatedError()
    meta = ensure_jwt_keys(settings.jwt_keys_path, allow_generate=settings.allow_generate_jwt_keys)
    try:
        header = jwt.get_unverified_header(token)
    except InvalidTokenError as exc:
        raise UnauthenticatedError("访问令牌无效") from exc
    kid = header.get("kid")
    if not isinstance(kid, str):
        raise UnauthenticatedError("访问令牌无效")
    allowed_kids = {meta["current_kid"]}
    if previous := meta.get("previous_kid"):
        allowed_kids.add(previous)
    if kid not in allowed_kids:
        raise UnauthenticatedError("访问令牌无效")
    try:
        return jwt.decode(
            token,
            load_public_pem(settings.jwt_keys_path, kid),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except InvalidTokenError as exc:
        raise UnauthenticatedError("访问令牌无效或已过期") from exc
