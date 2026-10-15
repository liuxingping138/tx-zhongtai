"""测试统一准备的环境变量：导入应用模块前 Settings 就需要它们。值只用于单测，不连真实服务。"""

import os
import tempfile

os.environ.setdefault("AI_AUDIT_INGEST_SECRET", "unit-test")
os.environ.setdefault("AI_DATABASE_URL", "postgresql+asyncpg://ai_app:test@localhost:5432/ai_db")
os.environ.setdefault("AI_IAM_SERVICE_SECRET", "unit-test")
os.environ.setdefault("AI_DATA_DIR", tempfile.mkdtemp(prefix="ai-service-test-"))
