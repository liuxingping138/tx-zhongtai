"""认证用例：登录、刷新、退出、改密。"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from platform_common.errors import ApiError, UnauthenticatedError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utcnow
from app.core.config import Settings
from app.core.jwt_tokens import issue_access_token
from app.core.rate_limit import login_key_username
from app.domain.enums import UserStatus
from app.domain.models import RefreshToken, Session, User
from app.domain.password import hash_password, needs_rehash, validate_password_policy, verify_password
from app.domain.tokens import generate_refresh_token, hash_refresh_token
from app.repositories import outbox as outbox_repo
from app.repositories import sessions as session_repo
from app.repositories import users as user_repo

UNIFIED_LOGIN_FAILURE = "用户名或密码错误"


def normalize_username(username: str) -> str:
    # 与登录限流的键共用一处规范化，两边不一致时换个大小写就能绕开账号锁定。
    return login_key_username(username)


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def authenticate_password(self, username: str, password: str) -> User:
        normalized = normalize_username(username)
        user = await user_repo.get_user_by_username(self.session, normalized)
        if user is None or not verify_password(user.password_hash, password):
            raise UnauthenticatedError(UNIFIED_LOGIN_FAILURE)
        if user.status != UserStatus.ACTIVE:
            raise UnauthenticatedError("账号不可用")
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        return user

    async def issue_session(
        self,
        user: User,
        *,
        client_info: dict[str, Any] | None,
        family_id: uuid.UUID | None = None,
    ) -> tuple[str, str, Session]:
        now = utcnow()
        session_row = Session(
            id=uuid.uuid4(),
            user_id=user.id,
            family_id=family_id or uuid.uuid4(),
            created_at=now,
            expires_at=now + timedelta(seconds=self.settings.refresh_token_ttl_seconds),
            last_seen_at=now,
            client_info=client_info,
        )
        raw_refresh = generate_refresh_token()
        refresh_row = RefreshToken(
            session_id=session_row.id,
            token_hash=hash_refresh_token(raw_refresh),
            issued_at=now,
            expires_at=session_row.expires_at,
        )
        self.session.add(session_row)
        await self.session.flush()
        self.session.add(refresh_row)
        access = issue_access_token(user_id=user.id, session_id=session_row.id, settings=self.settings)
        return access, raw_refresh, session_row

    async def login_success(
        self,
        user: User,
        *,
        request_id: str | None,
        client_ip: str,
        user_agent: str,
    ) -> tuple[str, str, Session]:
        access, refresh, session_row = await self.issue_session(
            user,
            client_info={"ip": client_ip, "user_agent": user_agent},
        )
        await outbox_repo.enqueue(
            self.session,
            event_type="auth.login.succeeded",
            payload={
                "actor_id": str(user.id),
                "actor_name": user.display_name,
                "username": user.username,
                "session_id": str(session_row.id),
                "request_id": request_id,
                "client_ip": client_ip,
                "outcome": "success",
            },
        )
        return access, refresh, session_row

    async def record_login_failure(
        self,
        *,
        username: str,
        request_id: str | None,
        client_ip: str,
        reason: str,
    ) -> None:
        await outbox_repo.enqueue(
            self.session,
            event_type="auth.login.failed",
            payload={
                "username": normalize_username(username),
                "request_id": request_id,
                "client_ip": client_ip,
                "reason": reason,
                "outcome": "failure",
            },
        )

    async def refresh(self, raw_refresh: str) -> tuple[str, str | None, Session, User]:
        token_hash = hash_refresh_token(raw_refresh)
        refresh_row = await session_repo.get_refresh_token_for_update(self.session, token_hash)
        now = utcnow()
        if refresh_row is None:
            raise UnauthenticatedError("刷新凭据无效")
        session_row = await session_repo.get_session(self.session, refresh_row.session_id)
        if session_row is None:
            raise UnauthenticatedError("刷新凭据无效")
        if refresh_row.consumed_at is not None:
            grace = timedelta(seconds=self.settings.refresh_reuse_grace_seconds)
            if (
                refresh_row.replaced_by is not None
                and refresh_row.consumed_at + grace >= now
                and session_repo.session_is_usable(session_row, now=now)
            ):
                user = await user_repo.get_user_by_id(self.session, session_row.user_id)
                if user is None or user.status != UserStatus.ACTIVE:
                    raise UnauthenticatedError("账号不可用")
                session_row.last_seen_at = now
                access = issue_access_token(user_id=user.id, session_id=session_row.id, settings=self.settings)
                return access, None, session_row, user
            await session_repo.revoke_family(self.session, session_row.family_id, now=now)
            await outbox_repo.enqueue(
                self.session,
                event_type="auth.refresh.replayed",
                payload={
                    "actor_id": str(session_row.user_id),
                    "session_id": str(session_row.id),
                    "family_id": str(session_row.family_id),
                    "outcome": "denied",
                },
            )
            raise UnauthenticatedError("刷新凭据已失效")
        if refresh_row.expires_at <= now or not session_repo.session_is_usable(session_row, now=now):
            raise UnauthenticatedError("刷新凭据已过期")
        user = await user_repo.get_user_by_id(self.session, session_row.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise UnauthenticatedError("账号不可用")

        refresh_row.consumed_at = now
        new_raw = generate_refresh_token()
        new_refresh = RefreshToken(
            session_id=session_row.id,
            token_hash=hash_refresh_token(new_raw),
            issued_at=now,
            expires_at=session_row.expires_at,
        )
        await self.session.flush()
        self.session.add(new_refresh)
        await self.session.flush()
        refresh_row.replaced_by = new_refresh.id
        session_row.last_seen_at = now
        access = issue_access_token(user_id=user.id, session_id=session_row.id, settings=self.settings)
        return access, new_raw, session_row, user

    async def logout(self, session_row: Session) -> None:
        now = utcnow()
        await session_repo.revoke_session(self.session, session_row, now=now)
        await outbox_repo.enqueue(
            self.session,
            event_type="auth.logout",
            payload={
                "actor_id": str(session_row.user_id),
                "session_id": str(session_row.id),
                "outcome": "success",
            },
        )

    async def logout_all(self, user: User) -> int:
        count = await session_repo.revoke_user_sessions(self.session, user.id)
        await outbox_repo.enqueue(
            self.session,
            event_type="auth.logout_all",
            payload={"actor_id": str(user.id), "revoked_count": count, "outcome": "success"},
        )
        return count

    async def change_password(self, user: User, old_password: str, new_password: str) -> tuple[str, str, Session]:
        if not verify_password(user.password_hash, old_password):
            raise UnauthenticatedError("原密码不正确")
        policy_error = validate_password_policy(new_password)
        if policy_error:
            raise ApiError(policy_error)
        if old_password == new_password:
            raise ApiError("新密码不能与原密码相同")
        now = utcnow()
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        user.password_changed_at = now
        user.updated_at = now
        user.version += 1
        await session_repo.revoke_user_sessions(self.session, user.id, now=now)
        access, refresh, session_row = await self.issue_session(
            user,
            client_info={"reason": "password_changed"},
        )
        await outbox_repo.enqueue(
            self.session,
            event_type="auth.password.changed",
            payload={
                "actor_id": str(user.id),
                "actor_name": user.display_name,
                "outcome": "success",
            },
        )
        return access, refresh, session_row
