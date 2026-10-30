"""工程规范里 ruff / ESLint 管不到的几条：Python 源文件不超过 400 行；忽略注释必须写原因；
数据库会话依赖必须是 function 作用域；前端页面和组件不写色值；迁移里给大表建索引要用 CONCURRENTLY。"""

from __future__ import annotations

import ast
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
# 默认 request 作用域在响应发出后才提交事务，提交失败时客户端已收到成功响应。
SESSION_DEPENDS = re.compile(r"Depends\(\s*get_db_session\s*\)")
# 颜色只在 frontend/src/styles 的主题变量里定义，页面和组件引用变量；各写各的色值，全站就统一不起来。
UI_SOURCE = re.compile(r"^frontend/src/(modules|components|layouts|views)/.+\.(vue|ts|css)$")
COLOR_LITERAL = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b|\brgba?\(\s*\d")
# Element 的状态色在 theme.css 里已换成主题色，页面直接引用它会绕开文字用的 text 档；页面用 --zt-success-text 这一组。
EL_STATUS_COLOR = re.compile(r"var\(--el-color-(?:success|warning|danger|error|info)\b")
# 本来就要写色值的文件登记在这里，写明理由。
COLOR_FILES: dict[str, str] = {
    "frontend/src/views/LoginView.vue": "登录页沿用原独立视觉",
    "frontend/src/modules/ai/billing/billing.ts": "费用账单的分类色板，按名字固定颜色，校验过色盲和对比度",
    "frontend/src/components/charts/echarts.ts": "图表取色在拿不到主题变量时的兜底值",
}


# 几十万到几百万行的表：普通 CREATE INDEX 建索引期间锁住写入，大表要几分钟，打标、导入、审计入库全部卡住。
# 用 op.create_index(..., postgresql_concurrently=True) 或 CREATE INDEX CONCURRENTLY，放在 autocommit_block 里。
BIG_TABLES = frozenset({"policy_base_tags", "policy_interpretations", "policy_crawler_site_daily", "audit_events"})
MIGRATION = re.compile(r"^services/[^/]+/migrations/versions/.+\.py$")
PLAIN_INDEX_SQL = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?!CONCURRENTLY)(?:IF\s+NOT\s+EXISTS\s+)?\S+\s+ON\s+(\w+)", re.I
)
# 这条规则之前已经上线的迁移：当时表还小或是建表时一起建，改历史迁移没有意义。
INDEX_LOCK_BASELINE: dict[str, str] = {
    "services/audit-service/migrations/versions/c2b8d4e7a201_p2_audit_events.py": "建表时一起建",
    "services/policy-service/migrations/versions/d4e1f2a3b401_init_policy.py": "建表时一起建",
    "services/policy-service/migrations/versions/a2b3c4d5e520_policy_ai_interpretation.py": "已上线，当时表很小",
    "services/policy-service/migrations/versions/c1d2e3f4a258_policy_title_trgm.py": "已上线，当时表很小",
    "services/policy-service/migrations/versions/d2e3f4a5b369_policy_filter_indexes.py": "已上线，当时表很小",
    "services/policy-service/migrations/versions/f7a8b9c0d035_base_tag_type_retag.py": "已上线，当时表很小",
    "services/policy-service/migrations/versions/a7b4c5d6e704_missing_searchable_indexes.py": (
        "已上线，当时表很小；表名在循环里，检查原来认不出来"
    ),
}


# 表名写成变量（循环里取常量元组、f-string 拼 SQL）时认不出是哪张表，用这个占位，再看整个迁移文件里出现过哪些大表。
_VARIABLE_TABLE = "__variable_table__"


def _index_table(call: ast.Call) -> str | None:
    named = next((kw.value for kw in call.keywords if kw.arg == "table_name"), None)
    table = call.args[1] if len(call.args) > 1 else named
    if table is None:
        return None
    return table.value if isinstance(table, ast.Constant) and isinstance(table.value, str) else _VARIABLE_TABLE


def _concurrent(call: ast.Call) -> bool:
    return any(
        kw.arg == "postgresql_concurrently" and isinstance(kw.value, ast.Constant) and kw.value.value is True
        for kw in call.keywords
    )


def _sql_text(node: ast.AST) -> str | None:
    """SQL 字符串；f-string 把各段拼回来，插值处换成占位表名。"""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value if isinstance(part, ast.Constant) and isinstance(part.value, str) else _VARIABLE_TABLE
            for part in node.values
        )
    return None


def _plain_index_tables(node: ast.AST, module_tables: frozenset[str]) -> list[tuple[int, str]]:
    """普通（不带 CONCURRENTLY）建索引落在哪些大表上：op.create_index 调用和 SQL 字符串两种写法。
    表名是变量时按这个迁移文件里出现过的大表算：原来只认字面量，循环建索引、f-string 拼 SQL 都能绕过去。"""

    def big(lineno: int, table: str) -> list[tuple[int, str]]:
        tables = module_tables if table == _VARIABLE_TABLE else {table} & BIG_TABLES
        return [(lineno, name) for name in sorted(tables)]

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "create_index":
        table = _index_table(node)
        return big(node.lineno, table) if table and not _concurrent(node) else []
    text = _sql_text(node)
    if text is None:
        return []
    return [item for match in PLAIN_INDEX_SQL.finditer(text) for item in big(node.lineno, match.group(1))]


def index_lock_errors(rel: str, source: str) -> list[str]:
    if rel in INDEX_LOCK_BASELINE:
        return []
    tree = ast.parse(source)
    # f-string 里的各段常量 ast.walk 还会单独走到一遍，跳过它们，免得同一处报两次。
    parts = {id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values}
    module_tables = frozenset(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in BIG_TABLES
    )
    found = {
        item
        for node in ast.walk(tree)
        if id(node) not in parts
        for item in _plain_index_tables(node, module_tables)
    }
    return [
        f"{rel}:{line}: 给大表 {table} 建索引要用 CONCURRENTLY（放在 autocommit_block 里）"
        for line, table in sorted(found)
    ]


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


def session_scope_errors(rel: str, source: str) -> list[str]:
    return [
        f'{rel}:{number}: 写成 Depends(get_db_session, scope="function")，否则提交失败也会返回成功'
        for number, line in enumerate(source.splitlines(), start=1)
        if SESSION_DEPENDS.search(line)
    ]


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


def color_literal_errors(rel: str, source: str) -> list[str]:
    if rel in COLOR_FILES or rel.endswith(".test.ts"):
        return []
    errors: list[str] = []
    for number, line in enumerate(source.splitlines(), start=1):
        if COLOR_LITERAL.search(line):
            errors.append(f"{rel}:{number}: 页面和组件里不写色值，用 theme.css 的变量（如 var(--zt-warning-text)）")
        if EL_STATUS_COLOR.search(line):
            errors.append(f"{rel}:{number}: 不直接用 Element 的状态色，用 theme.css 的 --zt-success / --zt-warning / --zt-danger 这一组")
    return errors


def line_count_errors(rel: str, source: str) -> list[str]:
    count = source.count("\n")
    if count > MAX_LINES and rel not in LONG_FILES:
        return [f"{rel}: {count} 行，超过 {MAX_LINES} 行；拆分，或在 LONG_FILES 登记理由"]
    return []


def check(files: list[str], root: Path) -> list[str]:
    errors: list[str] = []
    for rel in files:
        if MIGRATION.match(rel) and (root / rel).is_file():
            errors += index_lock_errors(rel, (root / rel).read_text(encoding="utf-8"))
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
            if not _is_python_test(rel):
                errors += session_scope_errors(rel, source)
            if PY_SOURCE.match(rel) and not _is_python_test(rel):
                errors += line_count_errors(rel, source)
        else:
            errors += frontend_comment_errors(rel, source)
            if UI_SOURCE.match(rel):
                errors += color_literal_errors(rel, source)
    stale = sorted(rel for rel in LONG_FILES if rel not in files)
    errors += [f"LONG_FILES 里的 {rel} 已不存在，删掉这条登记" for rel in stale]
    # 只在扫到前端页面时核对颜色登记，单独检查 Python 文件时不报。
    if any(UI_SOURCE.match(rel) for rel in files):
        stale = sorted(rel for rel in COLOR_FILES if rel not in files)
        errors += [f"COLOR_FILES 里的 {rel} 已不存在，删掉这条登记" for rel in stale]
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
