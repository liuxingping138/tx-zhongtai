"""工程规范里 ruff / ESLint 管不到的两条：Python 源文件不超过 400 行；忽略注释必须写原因。"""

from __future__ import annotations

import io
import re
import sys
import tokenize
from pathlib import Path

from scan_scope import ROOT, tracked_files

MAX_LINES = 400
# 确需超过 400 行的 Python 源文件登记在这里，写明理由（路径相对仓库根目录）。前端由 ESLint 的 max-lines 管。
LONG_FILES: dict[str, str] = {}

PY_SOURCE = re.compile(r"^(services/[^/]+/app|packages/platform-common/platform_common|scripts)/.+\.py$")
FRONTEND = re.compile(r"^frontend/(src|e2e)/.+\.(ts|vue)$|^frontend/[^/]+\.(ts|js)$")

NOQA = re.compile(r"#\s*noqa(?P<codes>:\s*[A-Z]+[0-9]+(?:\s*,\s*[A-Z]+[0-9]+)*)?(?P<rest>.*)", re.I)
TYPE_IGNORE = re.compile(r"#\s*type:\s*ignore(?P<codes>\[[^\]]*\])?(?P<rest>.*)")
ESLINT_DISABLE = re.compile(r"eslint-disable(?:-next-line|-line)?\b(?P<rest>[^*]*)")
TS_DIRECTIVE = re.compile(r"@ts-(?P<kind>ignore|nocheck|expect-error)\b(?P<rest>.*)")


def _is_python_test(rel: str) -> bool:
    return "/tests/" in rel or rel.startswith("tests/") or Path(rel).name.startswith("test_")


def _reason(rest: str) -> str:
    return rest.strip().lstrip("#").strip()


def python_comment_errors(rel: str, source: str) -> list[str]:
    """只看真正的注释 token：字符串里出现的 `# noqa` 字样不算。"""

    errors: list[str] = []
    # 测试目录不跑 mypy（make check 只检查 app/），测试里的 type: ignore 不生效，不要求原因。
    check_type_ignore = not _is_python_test(rel)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, SyntaxError):
        return [f"{rel}: 无法解析"]
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        where = f"{rel}:{token.start[0]}"
        if match := NOQA.search(token.string):
            if not match.group("codes"):
                errors.append(f"{where}: noqa 必须写明规则码")
            elif not _reason(match.group("rest")):
                errors.append(f"{where}: noqa 缺少原因，写成 `# noqa: <规则>  <原因>`")
        if check_type_ignore and (match := TYPE_IGNORE.search(token.string)):
            rest = match.group("rest")
            if not match.group("codes"):
                errors.append(f"{where}: type: ignore 必须写明错误码")
            elif not rest.strip().startswith("#") or not _reason(rest):
                errors.append(f"{where}: type: ignore 缺少原因，写成 `# type: ignore[<码>]  # <原因>`")
    return errors


def frontend_comment_errors(rel: str, source: str) -> list[str]:
    errors: list[str] = []
    for number, line in enumerate(source.splitlines(), start=1):
        where = f"{rel}:{number}"
        if (match := ESLINT_DISABLE.search(line)) and ("//" in line or "/*" in line):
            rest = match.group("rest")
            if "--" not in rest or not rest.split("--", 1)[1].strip():
                errors.append(f"{where}: eslint-disable 缺少原因，写成 `eslint-disable-next-line <规则> -- <原因>`")
        if (match := TS_DIRECTIVE.search(line)) and "//" in line:
            if match.group("kind") != "expect-error":
                errors.append(f"{where}: 不用 @ts-{match.group('kind')}，确需时用 @ts-expect-error 并写原因")
            elif not match.group("rest").strip():
                errors.append(f"{where}: @ts-expect-error 缺少原因")
    return errors


def line_count_errors(rel: str, source: str) -> list[str]:
    count = source.count("\n")
    if count > MAX_LINES and rel not in LONG_FILES:
        return [f"{rel}: {count} 行，超过 {MAX_LINES} 行；拆分，或在 LONG_FILES 登记理由"]
    return []


def check(files: list[str], root: Path) -> list[str]:
    errors: list[str] = []
    for rel in files:
        is_python = rel.endswith(".py") and "/migrations/versions/" not in rel
        is_frontend = bool(FRONTEND.match(rel))
        if not (is_python or is_frontend):
            continue
        path = root / rel
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        if is_python:
            errors += python_comment_errors(rel, source)
            if PY_SOURCE.match(rel) and not _is_python_test(rel):
                errors += line_count_errors(rel, source)
        else:
            errors += frontend_comment_errors(rel, source)
    stale = sorted(rel for rel in LONG_FILES if rel not in files)
    errors += [f"LONG_FILES 里的 {rel} 已不存在，删掉这条登记" for rel in stale]
    return errors


def main() -> int:
    errors = check(tracked_files(), ROOT)
    if errors:
        print("\n".join(errors))
        return 1
    print("code_rules_ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
