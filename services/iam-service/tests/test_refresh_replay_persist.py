"""宽限期外重放的撤销和审计必须在 401 之后仍能被另一个事务看见。"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

os.environ.setdefault("IAM_DATABASE_URL", "postgresql+asyncpg://iam_app:test@localhost:5432/iam_db")
os.environ.setdefault("IAM_REDIS_URL", "redis://localhost:6379/0")

import pytest  # noqa: E402
from platform_common.errors import UnauthenticatedError  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB, UUID  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.core.database as database  # noqa: E402
from app.application.auth_service import AuthService  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.database import get_db_session  # noqa: E402
from app.domain.enums import UserStatus  # noqa: E402
from app.domain.models import Base, OutboxEvent, RefreshToken, Session, User  # noqa: E402
from app.domain.tokens import hash_refresh_token  # noqa: E402

# SQLite 不保留时区。这里用同一套无时区时间，只验证事务提交；线上 Postgres 存的是带时区时间。
_NOW = datetime(2026, 10, 8, 9, 0)


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw):  # type: ignore[no-untyped-def]
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw):  # type: ignore[no-untyped-def]
    return "CHAR(36)"


def _settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/0",
        environment="test",  # type: ignore[arg-type]
        refresh_reuse_grace_seconds=30,
    )


async def _call(service_session_factory, raw: str, settings: Settings):  # type: ignore[no-untyped-def]
    del service_session_factory
    generator = get_db_session()
    session = await anext(generator)
    service = AuthService(session, settings)
    try:
        result = await service.refresh(raw)
    except UnauthenticatedError as exc:
        with pytest.raises(UnauthenticatedError):
            await generator.athrow(exc)
        return None
    try:
        await anext(generator)
    except StopAsyncIteration:
        pass
    return result


async def _seed(factory, *, consumed_age: timedelta, raw: str, replacement: str):  # type: ignore[no-untyped-def]
    async with factory() as session:
        user = User(
            username=f"replay-{uuid.uuid4().hex[:8]}",
            display_name="重放",
            password_hash="not-used",
            status=UserStatus.ACTIVE,
            must_change_password=False,
            version=1,
            created_at=_NOW,
            updated_at=_NOW,
        )
        session.add(user)
        await session.flush()
        login = Session(
            user_id=user.id,
            family_id=uuid.uuid4(),
            created_at=_NOW - timedelta(hours=1),
            expires_at=_NOW + timedelta(days=1),
            last_seen_at=_NOW - timedelta(hours=1),
        )
        session.add(login)
        await session.flush()
        old = RefreshToken(
            session_id=login.id,
            token_hash=hash_refresh_token(raw),
            issued_at=_NOW - timedelta(hours=1),
            expires_at=_NOW + timedelta(days=1),
            consumed_at=_NOW - consumed_age,
        )
        session.add(old)
        await session.flush()
        new = RefreshToken(
            session_id=login.id,
            token_hash=hash_refresh_token(replacement),
            issued_at=_NOW - timedelta(minutes=1),
            expires_at=_NOW + timedelta(days=1),
        )
        session.add(new)
        await session.flush()
        old.replaced_by = new.id
        await session.commit()
        return login.id


@pytest.fixture
async def sqlite_sessions(monkeypatch: pytest.MonkeyPatch):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr("app.application.auth_service.utcnow", lambda: _NOW)
    monkeypatch.setattr("app.repositories.sessions.utcnow", lambda: _NOW)
    monkeypatch.setattr("app.repositories.outbox.utcnow", lambda: _NOW)
    monkeypatch.setattr("app.application.auth_service.issue_access_token", lambda **_kwargs: "access-token")
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_replay_outside_grace_stays_revoked_after_request_rollback(sqlite_sessions) -> None:  # type: ignore[no-untyped-def]
    settings = _settings()
    old_raw = "old-refresh-token-outside-grace"
    new_raw = "new-refresh-token-outside-grace"
    session_id = await _seed(sqlite_sessions, consumed_age=timedelta(seconds=31), raw=old_raw, replacement=new_raw)

    outcome = await _call(sqlite_sessions, old_raw, settings)
    assert outcome is None

    async with sqlite_sessions() as other:
        login = await other.get(Session, session_id)
        assert login is not None
        assert login.revoked_at == _NOW
        found = await other.execute(select(OutboxEvent).where(OutboxEvent.event_type == "auth.refresh.replayed"))
        events = found.scalars().all()
        assert len(events) == 1

    again = await _call(sqlite_sessions, new_raw, settings)
    assert again is None
    async with sqlite_sessions() as other:
        login = await other.get(Session, session_id)
        assert login is not None
        assert login.revoked_at == _NOW


@pytest.mark.asyncio
async def test_replay_inside_grace_succeeds_and_does_not_revoke(sqlite_sessions) -> None:  # type: ignore[no-untyped-def]
    settings = _settings()
    old_raw = "old-refresh-token-inside-grace"
    new_raw = "new-refresh-token-inside-grace"
    session_id = await _seed(sqlite_sessions, consumed_age=timedelta(seconds=5), raw=old_raw, replacement=new_raw)

    access, rotated, _row, user = await _call(sqlite_sessions, old_raw, settings)
    assert access == "access-token"
    assert rotated is None
    assert user.status == UserStatus.ACTIVE

    async with sqlite_sessions() as other:
        login = await other.get(Session, session_id)
        assert login is not None
        assert login.revoked_at is None
        found = await other.execute(select(OutboxEvent).where(OutboxEvent.event_type == "auth.refresh.replayed"))
        replayed = found.scalars().all()
        assert replayed == []

    # 宽限期内再次使用旧令牌仍然成功，不撤销会话族。
    second, rotated_again, _, _ = await _call(sqlite_sessions, old_raw, settings)
    assert second == "access-token"
    assert rotated_again is None
    fresh = await _call(sqlite_sessions, new_raw, settings)
    assert fresh is not None
    assert fresh[0] == "access-token"
