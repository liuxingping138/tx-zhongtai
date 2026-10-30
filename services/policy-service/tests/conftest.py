"""测试统一准备的环境变量：导入应用模块前 Settings 就需要它们。值只用于单测，不连真实服务。

用 setdefault：调度集成测试等需要真实库的用例，可以从外部传入同名变量覆盖。
"""

import os

os.environ.setdefault("POLICY_AUDIT_INGEST_SECRET", "unit-test")
os.environ.setdefault("POLICY_DATABASE_URL", "postgresql+asyncpg://policy_app:test@localhost:5432/policy_db")
os.environ.setdefault("POLICY_IAM_SERVICE_SECRET", "unit-test")


import pytest


@pytest.fixture(autouse=True)
def _no_previous_ai_run(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """打标每批会连库查上一批失败的 AI 任务、读到的政策打没打过标，还会去 ai-service 复核模板：
    单测默认都没有、都通过，测这些的用例自己覆盖。"""

    from app.aitag.repositories import tagging

    async def none(*_: object, **__: object) -> str:
        return ""

    if not request.node.get_closest_marker("real_failed_run"):
        monkeypatch.setattr(tagging, "failed_ai_run", none)

    async def no_tagged(*_: object, **__: object) -> set[str]:
        return set()

    async def template_ok(*_: object, **__: object) -> None:
        return None

    from app.aitag.application import tagging as tagging_app

    monkeypatch.setattr(tagging, "tagged_source_ids", no_tagged)
    if not request.node.get_closest_marker("real_template_check"):
        monkeypatch.setattr(tagging_app, "check_template_now", template_ok)
