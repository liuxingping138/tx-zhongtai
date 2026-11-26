"""并发新增撞唯一约束回 409；其他完整性错误仍是 500。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from platform_common.errors import register_exception_handlers


class _PgError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


def _integrity(sqlstate: str) -> IntegrityError:
    return IntegrityError("INSERT ...", {}, _PgError(sqlstate))


async def _commit_on_exit() -> AsyncIterator[None]:
    """模拟 get_db_session：路由返回后才提交，冲突在这里才暴露。"""

    yield
    raise _integrity("23505")


def _app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/flush-unique")
    async def flush_unique() -> None:
        raise _integrity("23505")

    @app.post("/flush-not-null")
    async def flush_not_null() -> None:
        raise _integrity("23502")

    @app.post("/commit-unique", dependencies=[Depends(_commit_on_exit, scope="function")])
    async def commit_unique() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_unique_violation_during_flush_is_409() -> None:
    response = TestClient(_app()).post("/flush-unique")
    assert response.status_code == 409
    assert response.json()["code"] == "DUPLICATE"


def test_unique_violation_during_commit_is_409() -> None:
    response = TestClient(_app(), raise_server_exceptions=False).post("/commit-unique")
    assert response.status_code == 409
    assert response.json()["code"] == "DUPLICATE"


def test_other_integrity_errors_stay_500() -> None:
    response = TestClient(_app(), raise_server_exceptions=False).post("/flush-not-null")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
