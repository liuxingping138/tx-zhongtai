"""check_code_rules 要拦住缺原因的忽略和超长文件，同时不能误报字符串里的字样。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_code_rules as rules  # noqa: E402  先把脚本目录加进 sys.path 才能导入

APP = "services/demo-service/app/x.py"
TEST = "services/demo-service/tests/test_x.py"
NOQA_BAD = "import os  # noqa: F401\n"
IGNORE_BAD = "x = f()  # type: ignore[arg-type]\n"


def test_python_suppressions_need_reason() -> None:
    assert rules.python_comment_errors(APP, NOQA_BAD)
    assert rules.python_comment_errors(APP, "import os  # noqa\n")
    assert rules.python_comment_errors(APP, IGNORE_BAD)
    assert rules.python_comment_errors(APP, "x = f()  # type: ignore[arg-type]  原因\n"), "mypy 不认这种写法"
    assert rules.python_comment_errors(APP, "x = f()  # type: ignore  # 原因\n"), "必须写错误码"
    assert not rules.python_comment_errors(APP, "import os  # noqa: F401  重新导出\n")
    assert not rules.python_comment_errors(APP, "x = f()  # type: ignore[arg-type]  # 替身对象\n")


def test_strings_and_test_type_ignores_are_not_reported() -> None:
    assert not rules.python_comment_errors(APP, 'TEXT = "# noqa: F401"\n')
    assert not rules.python_comment_errors(TEST, IGNORE_BAD)
    assert rules.python_comment_errors(TEST, NOQA_BAD), "测试同样跑 ruff，noqa 仍要原因"


def test_frontend_suppressions_need_reason() -> None:
    rel = "frontend/src/x.ts"
    assert rules.frontend_comment_errors(rel, "// eslint-disable-next-line no-console\n")
    assert rules.frontend_comment_errors(rel, "// @ts-ignore\n")
    assert rules.frontend_comment_errors(rel, "// @ts-expect-error\n")
    assert not rules.frontend_comment_errors(rel, "// eslint-disable-next-line no-console -- 调试入口\n")
    assert not rules.frontend_comment_errors(rel, "// @ts-expect-error 第三方类型缺字段\n")


def test_session_dependency_must_be_function_scoped() -> None:
    assert rules.session_scope_errors(APP, "s: AsyncSession = Depends(get_db_session),\n")
    assert not rules.session_scope_errors(APP, 's: AsyncSession = Depends(get_db_session, scope="function"),\n')


def test_long_python_source_is_reported_unless_registered() -> None:
    long_source = "x = 1\n" * (rules.MAX_LINES + 1)
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        for rel in (APP, TEST):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(long_source, encoding="utf-8")
        assert rules.check([APP, TEST], root) == rules.line_count_errors(APP, long_source)
        rules.LONG_FILES[APP] = "示例"
        try:
            assert not rules.check([APP, TEST], root)
            assert rules.check([TEST], root), "登记了但文件已不存在要提示清理"
        finally:
            del rules.LONG_FILES[APP]


def test_ui_color_literals_are_reported_outside_registered_files() -> None:
    page = "frontend/src/modules/demo/Page.vue"
    assert rules.color_literal_errors(page, ".tag { color: #9a6418; }\n")
    assert rules.color_literal_errors(page, "box-shadow: 0 0 4px rgba(0, 0, 0, 0.2);\n")
    assert rules.color_literal_errors(page, "background: #fff;\n")
    assert not rules.color_literal_errors(page, ".tag { color: var(--zt-warning-text); }\n")
    assert rules.color_literal_errors(page, ".bad { color: var(--el-color-danger); }\n"), "Element 状态色绕开主题的 text 档"
    assert not rules.color_literal_errors(page, ".on { background: var(--el-color-primary-light-9); }\n")
    assert not rules.color_literal_errors(page, '<a href="#industry">行业</a>\n'), "锚点不是颜色"
    assert not rules.color_literal_errors(page, "return `rgba(${r}, ${g}, ${b}, ${alpha})`\n"), "按变量拼的颜色不算写死"
    assert not rules.color_literal_errors("frontend/src/modules/demo/page.test.ts", "expect(c).toBe('#fff')\n")
    assert not rules.color_literal_errors("frontend/src/views/LoginView.vue", "color: #fff;\n")


if __name__ == "__main__":
    test_python_suppressions_need_reason()
    test_strings_and_test_type_ignores_are_not_reported()
    test_frontend_suppressions_need_reason()
    test_session_dependency_must_be_function_scoped()
    test_long_python_source_is_reported_unless_registered()
    test_ui_color_literals_are_reported_outside_registered_files()
    print("code_rules_selftest_ok")
