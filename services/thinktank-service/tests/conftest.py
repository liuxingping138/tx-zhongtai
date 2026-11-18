"""测试统一准备的环境变量：导入应用模块前 Settings 就需要它们。值只用于单测，不连真实服务。"""

import os
import tempfile

os.environ.setdefault("THINKTANK_AUDIT_INGEST_SECRET", "unit-test")
os.environ.setdefault("THINKTANK_DATABASE_URL", "postgresql+asyncpg://thinktank_app:test@localhost:5432/thinktank_db")
os.environ.setdefault("THINKTANK_IAM_SERVICE_SECRET", "unit-test")
os.environ.setdefault("THINKTANK_STORAGE_DIR", tempfile.mkdtemp(prefix="thinktank-test-"))
