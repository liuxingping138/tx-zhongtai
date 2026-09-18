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


def _dump(app: object, dest: Path) -> None:
    payload = app.openapi()  # type: ignore[attr-defined]
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {dest} paths={len(payload.get('paths', {}))}")


def main() -> int:
    _prepare_env()
    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / "services/iam-service"))
    from app.main import app as iam_app

    _dump(iam_app, OUT / "iam.json")
    sys.path.pop(0)
    for key in list(sys.modules):
        if key == "app" or key.startswith("app."):
            del sys.modules[key]
    sys.path.insert(0, str(ROOT / "services/audit-service"))
    from app.main import app as audit_app

    _dump(audit_app, OUT / "audit.json")
    for key in list(sys.modules):
        if key == "app" or key.startswith("app."):
            del sys.modules[key]
    sys.path.pop(0)
    sys.path.insert(0, str(ROOT / "services/codebook-service"))
    from app.main import app as codebook_app

    _dump(codebook_app, OUT / "codebook.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
