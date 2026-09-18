"""检查业务目录仍为空，且公开仓库文件不含明显密钥。"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUSINESS_DIRS = [
    ROOT / "frontend/src/modules/customer",
    ROOT / "frontend/src/modules/tender",
    ROOT / "services/customer-service",
    ROOT / "services/tender-service",
]
CODE_SUFFIX = {".py", ".ts", ".tsx", ".vue", ".js", ".sql"}
SECRET_RE = re.compile(
    r"(password\s*=\s*['\"](?!dev-only|p6-only|change-me)[^'\"]{8,}['\"]|"
    r"BEGIN (RSA |OPENSSH )?PRIVATE KEY)",
    re.I,
)


def _business_ok() -> list[str]:
    errors: list[str] = []
    for folder in BUSINESS_DIRS:
        if not folder.exists():
            errors.append(f"缺少占位目录 {folder}")
            continue
        unexpected = [
            path
            for path in folder.rglob("*")
            if path.is_file() and path.name != ".gitkeep" and path.suffix in CODE_SUFFIX
        ]
        if unexpected:
            errors.append(f"业务目录出现源码: {unexpected[0]}")
    return errors


def _secret_scan() -> list[str]:
    listed = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
    errors: list[str] = []
    skip = {"docs/openapi/iam.json", "docs/openapi/audit.json", "docs/openapi/codebook.json", "docs/openapi/policy.json"}
    for rel in listed:
        if rel in skip or rel.endswith(".lock") or "pnpm-lock" in rel:
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if SECRET_RE.search(text):
            errors.append(f"疑似密钥 {rel}")
    return errors


def main() -> int:
    errors = [*_business_ok(), *_secret_scan()]
    if errors:
        print("\n".join(errors))
        return 1
    print("scope_ok business_placeholder_only secrets_scan_clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
