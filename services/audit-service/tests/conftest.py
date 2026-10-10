"""测试统一准备的环境变量：导入应用模块前 Settings 就需要它们。值只用于单测，不连真实服务。

用 setdefault：调度集成测试等需要真实库的用例，可以从外部传入同名变量覆盖。
"""

import os

os.environ.setdefault("AUDIT_DATABASE_URL", "postgresql+asyncpg://audit_app:test@localhost:5432/audit_db")
os.environ.setdefault("AUDIT_INGEST_SECRET", "unit-test")
os.environ.setdefault("AUDIT_INTERNAL_CALLER_SECRETS", '{"iam-service":"unit-test-token"}')
