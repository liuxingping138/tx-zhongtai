"""从本地应用对象导出 OpenAPI，不访问运行中的容器网络。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "openapi"


def _prepare_env() -> None:
    os.environ.setdefault("IAM_DATABASE_URL", "postgresql+asyncpg://iam_app:test@localhost:5432/iam_db")
    os.environ.setdefault("IAM_REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("IAM_ENVIRONMENT", "test")
    os.environ.setdefault("AUDIT_DATABASE_URL", "postgresql+asyncpg://audit_app:test@localhost:5432/audit_db")
    os.environ.setdefault("AUDIT_ENVIRONMENT", "test")
    os.environ.setdefault("AUDIT_IAM_SERVICE_SECRET", "export-only")
    os.environ.setdefault("CODEBOOK_DATABASE_URL", "postgresql+asyncpg://codebook_app:test@localhost:5432/codebook_db")
    os.environ.setdefault("CODEBOOK_ENVIRONMENT", "test")
    os.environ.setdefault("CODEBOOK_IAM_SERVICE_SECRET", "export-only")
    os.environ.setdefault("CODEBOOK_AUDIT_INGEST_SECRET", "export-only")
    os.environ.setdefault("POLICY_DATABASE_URL", "postgresql+asyncpg://policy_app:test@localhost:5432/policy_db")
    os.environ.setdefault("POLICY_ENVIRONMENT", "test")
    os.environ.setdefault("POLICY_IAM_SERVICE_SECRET", "export-only")
    os.environ.setdefault("POLICY_AUDIT_INGEST_SECRET", "export-only")


def _dump(app: object, dest: Path) -> None:
    payload = app.openapi()  # type: ignore[attr-defined]
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {dest} paths={len(payload.get('paths', {}))}")


SERVICES = {
    "iam": "services/iam-service",
    "audit": "services/audit-service",
    "codebook": "services/codebook-service",
    "policy": "services/policy-service",
}


def main() -> int:
    _prepare_env()
    OUT.mkdir(parents=True, exist_ok=True)
    wanted = sys.argv[1:] or list(SERVICES)
    for name in wanted:
        rel = SERVICES[name]
        sys.path.insert(0, str(ROOT / rel))
        from app.main import app as service_app

        _dump(service_app, OUT / f"{name}.json")
        del sys.modules["app"]
        for key in list(sys.modules):
            if key.startswith("app."):
                del sys.modules[key]
        sys.path.pop(0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
