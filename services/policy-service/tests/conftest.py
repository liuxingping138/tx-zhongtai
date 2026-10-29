"""测试统一准备的环境变量：导入应用模块前 Settings 就需要它们。值只用于单测，不连真实服务。

用 setdefault：调度集成测试等需要真实库的用例，可以从外部传入同名变量覆盖。
"""

import os

os.environ.setdefault("POLICY_AUDIT_INGEST_SECRET", "unit-test")
os.environ.setdefault("POLICY_DATABASE_URL", "postgresql+asyncpg://policy_app:test@localhost:5432/policy_db")
os.environ.setdefault("POLICY_IAM_SERVICE_SECRET", "unit-test")


import pytest


@pytest.fixture(autouse=True)
def _no_previous_ai_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """打标每一步发起前会查上一批失败的 AI 任务（要连库）；单测默认没有，测沿用的用例自己覆盖。"""

    from app.aitag.repositories import tagging

    async def none(*_: object, **__: object) -> str:
        return ""

    monkeypatch.setattr(tagging, "failed_ai_run", none)
