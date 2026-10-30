"""认证用例：登录、刷新、退出、改密。"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from platform_common.clock import utcnow
from platform_common.errors import ApiError, ErrorCode, UnauthenticatedError
from platform_common.logging_setup import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import SideSessionLocal
from app.core.jwt_tokens import issue_access_token
from app.core.rate_limit import login_key_username
from app.domain.enums import UserStatus
from app.domain.models import RefreshToken, Session, User
from app.domain.password import (
    hash_password,
    hash_password_async,
    needs_rehash,
    validate_password_policy,
    verify_password_async,
)
from app.domain.tokens import generate_refresh_token, hash_refresh_token
from app.repositories import outbox as outbox_repo
from app.repositories import sessions as session_repo
from app.repositories import users as user_repo

logger = get_logger(__name__)


class WrongOldPasswordError(ApiError):
    """改密码时原密码不对。不能回 401：前端会当成会话过期，先续期再重发，每输错一次多跑两遍 Argon2。
    接口层据此按登录失败计数、留痕：拿到别人令牌的人原来能无限次试原密码，猜中就改掉密码、长期接管账号。"""

    def __init__(self) -> None:
        super().__init__("原密码不正确", code=ErrorCode.VALIDATION_ERROR, http_status=422)


UNIFIED_LOGIN_FAILURE = "用户名或密码错误"
ACCOUNT_UNAVAILABLE = "账号不可用"


def normalize_username(username: str) -> str:
    # 与登录限流的键共用一处规范化，两边不一致时换个大小写就能绕开账号锁定。
    return login_key_username(username)


# 登录、退出时从请求里取的 IP 和浏览器标识：{"ip": ..., "user_agent": ...}。
ClientInfo = dict[str, str]


def _client_fields(client: ClientInfo | None) -> dict[str, str]:
    """写进审计的 client_ip / user_agent，登录日志按这两个字段显示来源。"""

    if not client:
        return {}
    return {"client_ip": client.get("ip", ""), "user_agent": client.get("user_agent", "")}


# 给不存在的账号用的哈希，让登录失败的耗时和真账号一样。
_TIMING_HASH = hash_password("timing-equalizer-not-a-real-password")


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def authenticate_password(self, username: str, password: str) -> User:
        normalized = normalize_username(username)
        user = await user_repo.get_user_by_username(self.session, normalized)
        if user is None or user.status == UserStatus.DELETED:
            # 账号不存在也跑一次同样的哈希校验：否则按响应快慢就能试出哪些用户名是真的。
            await verify_password_async(_TIMING_HASH, password)
            raise UnauthenticatedError(UNIFIED_LOGIN_FAILURE)
        if not await verify_password_async(user.password_hash, password):
            raise UnauthenticatedError(UNIFIED_LOGIN_FAILURE)
        if user.status != UserStatus.ACTIVE:
            raise UnauthenticatedError(ACCOUNT_UNAVAILABLE)
        if needs_rehash(user.password_hash):
            user.password_hash = await hash_password_async(password)
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
        # 用户列表的「最近登录」读这两列：会话过期后会被清理，不能靠它倒推。
        user.last_login_at = session_row.created_at
        user.last_login_ip = client_ip[:64]
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
                "user_agent": user_agent,
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
        user_agent: str,
        reason: str,
    ) -> None:
        """登录失败留痕。输入的用户名能对上账号时记上这个人和显示名，和成功的那几行一样，
        按人筛登录日志才看得到把他锁住的那些失败；对不上的照旧只记输入的用户名。"""

        normalized = normalize_username(username)
        user = await user_repo.get_user_by_username(self.session, normalized)
        who = {} if user is None else {"actor_id": str(user.id), "actor_name": user.display_name}
        await outbox_repo.enqueue(
            self.session,
            event_type="auth.login.failed",
            payload={
                **who,
                "username": normalized,
                "request_id": request_id,
                "client_ip": client_ip,
                "user_agent": user_agent,
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
                    raise UnauthenticatedError(ACCOUNT_UNAVAILABLE)
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
            # 安全撤销必须持久化，再返回 401；请求依赖随后 rollback 不得撤销此结果。
            await self.session.commit()
            raise UnauthenticatedError("刷新凭据已失效")
        if refresh_row.expires_at <= now or not session_repo.session_is_usable(session_row, now=now):
            raise UnauthenticatedError("刷新凭据已过期")
        user = await user_repo.get_user_by_id(self.session, session_row.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            raise UnauthenticatedError(ACCOUNT_UNAVAILABLE)

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

    async def logout(self, session_row: Session, *, actor_name: str = "", client: ClientInfo | None = None) -> None:
        now = utcnow()
        await session_repo.revoke_session(self.session, session_row, now=now)
        await outbox_repo.enqueue(
            self.session,
            event_type="auth.logout",
            payload={
                "actor_id": str(session_row.user_id),
                "actor_name": actor_name,
                "session_id": str(session_row.id),
                **_client_fields(client),
                "outcome": "success",
            },
        )

    async def logout_all(self, user: User, *, client: ClientInfo | None = None) -> int:
        count = await session_repo.revoke_user_sessions(self.session, user.id)
        await outbox_repo.enqueue(
            self.session,
            event_type="auth.logout_all",
            payload={
                "actor_id": str(user.id),
                "actor_name": user.display_name,
                "revoked_count": count,
                **_client_fields(client),
                "outcome": "success",
            },
        )
        return count

    async def change_password(
        self, user: User, old_password: str, new_password: str, *, client: ClientInfo | None = None
    ) -> tuple[str, str, Session]:
        if not await verify_password_async(user.password_hash, old_password):
            raise WrongOldPasswordError()
        policy_error = validate_password_policy(new_password)
        if policy_error:
            raise ApiError(policy_error)
        if old_password == new_password:
            raise ApiError("新密码不能与原密码相同")
        now = utcnow()
        user.password_hash = await hash_password_async(new_password)
        user.must_change_password = False
        user.password_changed_at = now
        user.updated_at = now
        user.version += 1
        await session_repo.revoke_user_sessions(self.session, user.id, now=now)
        access, refresh, session_row = await self.issue_session(
            user,
            # 改密后换发的会话也记下 IP 和浏览器，在线用户里才认得出是哪台设备。
            client_info={**(client or {}), "reason": "password_changed"},
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


async def load_principal(session: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> tuple[User, Session]:
    """按访问令牌里的用户和会话编号加载登录主体；账号不可用、会话失效或与用户不匹配一律视为未登录。

    会话和账号一条查出：业务服务每个受保护请求都经 authorize 走到这里。
    """
    found = await session_repo.get_session_with_user(session, session_id, user_id)
    if found is None:
        raise UnauthenticatedError()
    session_row, user = found
    if user.status != UserStatus.ACTIVE:
        raise UnauthenticatedError("账号不可用")
    if not session_repo.session_is_usable(session_row):
        raise UnauthenticatedError()
    if session_row.user_id != user.id:
        raise UnauthenticatedError()
    return user, session_row


async def note_activity(session_row: Session, *, every_seconds: int) -> None:
    """在线用户的「最近活跃」：带令牌的请求（含业务服务经 authorize 的请求）都算一次操作。

    原来只在登录和刷新令牌时更新，访问令牌 8 小时才刷新一次，看不出谁 30 分钟内还在用。
    每台设备最多每 every_seconds 写一次库；写在独立的短事务里：请求自己的事务可能很长（如导入），
    在里面改这一行会让同一个人的其他请求等锁。写失败只记日志，不影响请求。
    """

    now = utcnow()
    stale_before = now - timedelta(seconds=every_seconds)
    if session_row.last_seen_at >= stale_before:
        return
    try:
        async with SideSessionLocal() as db:
            await session_repo.touch_last_seen(db, session_row.id, now=now, stale_before=stale_before)
            await db.commit()
    except Exception:  # noqa: BLE001  活跃时间写不进去不能让请求失败
        logger.warning("session_touch_failed", session_id=str(session_row.id))


async def role_summary(session: AsyncSession, user_id: uuid.UUID) -> tuple[bool, list[str]]:
    """是否内置超级管理员，以及角色名称列表（「我的信息」用）。"""
    return (
        await user_repo.user_has_builtin_superadmin(session, user_id),
        await user_repo.list_user_role_names(session, user_id),
    )
