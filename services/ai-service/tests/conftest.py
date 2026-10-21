"""测试统一准备的环境变量：导入应用模块前 Settings 就需要它们。值只用于单测，不连真实服务。"""

import os
import tempfile

import pytest

os.environ.setdefault("AI_AUDIT_INGEST_SECRET", "unit-test")
os.environ.setdefault("AI_DATABASE_URL", "postgresql+asyncpg://ai_app:test@localhost:5432/ai_db")
os.environ.setdefault("AI_IAM_SERVICE_SECRET", "unit-test")
os.environ.setdefault("AI_DATA_DIR", tempfile.mkdtemp(prefix="ai-service-test-"))


@pytest.fixture(autouse=True)
def model_table(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """模型配置表换成内存列表，用例可往里加、改。"""

    # 放在函数里导入：应用模块要等上面的环境变量设好再加载。
    from app.repositories import model_configs
    from tests.helpers import sample_models

    rows = sample_models()

    async def list_all(_session: object, *, enabled_only: bool = False) -> list[object]:
        return [row for row in rows if row.enabled or not enabled_only]

    async def get(_session: object, model_id: str, *, lock: bool = False) -> object | None:
        return next((row for row in rows if row.id == model_id), None)

    monkeypatch.setattr(model_configs, "list_all", list_all)
    monkeypatch.setattr(model_configs, "get", get)
    monkeypatch.setattr(model_configs, "add", lambda _session, row: rows.append(row))
    return rows  # type: ignore[return-value]
