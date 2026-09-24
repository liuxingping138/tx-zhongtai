"""会话/刷新令牌清理的单元测试。

只验证 SQL 语义（删哪些行、按什么顺序删），不连数据库。
真实数据库上的验证见 docs/guides/部署与维护.md 里的记录。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.dialects import postgresql

from app.application.session_cleanup import _cutoff, _dead_session_ids
from app.domain.models import RefreshToken, Session

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def _sql(stmt: object) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))  # type: ignore[attr-defined]


def test_cutoff_is_retention_days_before_now() -> None:
    assert _cutoff(30, now=NOW) == NOW - timedelta(days=30)
    assert _cutoff(0, now=NOW) == NOW


def test_dead_sessions_match_expired_or_revoked_only() -> None:
    sql = _sql(_dead_session_ids(_cutoff(30, now=NOW)).element)
    # 过期的会算进来
    assert "expires_at <" in sql
    # 撤销的也算，但必须先判非空，否则 NULL 比较恒为假
    assert "revoked_at IS NOT NULL" in sql
    assert "revoked_at <" in sql
    # 两个条件是 OR，不是 AND：任一成立即可回收
    assert " OR " in sql


def test_active_sessions_are_never_selected() -> None:
    """没有任何无条件删除：谓词里必须同时出现两个时间判断。"""

    sql = _sql(_dead_session_ids(_cutoff(30, now=NOW)).element)
    assert "WHERE" in sql
    assert sql.count("2026-08-22") == 2  # 30 天前，两处判断都用同一个 cutoff


def test_tokens_are_deleted_by_session_subquery() -> None:
    """令牌必须按「属于待回收会话」删除，而不是只看令牌自身过期时间。

    令牌自己过期不代表会话结束，按令牌过期删会把在用会话的历史删掉。
    """

    dead = _dead_session_ids(_cutoff(30, now=NOW))
    sql = _sql(delete(RefreshToken).where(RefreshToken.session_id.in_(dead)))
    assert "iam_refresh_tokens" in sql
    assert "session_id IN" in sql
    assert "iam_sessions" in sql  # 子查询指向会话表


def test_sessions_and_tokens_target_different_tables() -> None:
    dead = _dead_session_ids(_cutoff(30, now=NOW))
    token_sql = _sql(delete(RefreshToken).where(RefreshToken.session_id.in_(dead)))
    session_sql = _sql(delete(Session).where(Session.id.in_(dead)))
    assert token_sql.startswith("DELETE FROM iam_refresh_tokens")
    assert session_sql.startswith("DELETE FROM iam_sessions")
