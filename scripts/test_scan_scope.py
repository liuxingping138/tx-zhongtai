"""中文文件名必须进入密钥扫描，不能被 git 的引号转义悄悄跳过。"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_scope  # noqa: E402  先把脚本目录加进 sys.path 才能导入


def test_tracked_files_include_unicode_names() -> None:
    listed = scan_scope.tracked_files()
    chinese = [item for item in listed if any(ord(char) > 127 for char in item)]
    assert chinese, "仓库里的中文路径没有被列出来"
    existing = [item for item in chinese if (scan_scope.ROOT / item).is_file()]
    assert existing, "中文路径被列出来了，但扫描时会被当成不存在"


def test_secret_in_chinese_filename_is_reported() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        env = dict(**os.environ)
        env.update(
            {
                "GIT_AUTHOR_NAME": "scan",
                "GIT_AUTHOR_EMAIL": "scan@example.com",
                "GIT_COMMITTER_NAME": "scan",
                "GIT_COMMITTER_EMAIL": "scan@example.com",
            }
        )
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        target = root / "说明文档.txt"
        target.write_text('password' + ' = ' + repr('scan-fixture-only') + '\n', encoding="utf-8")
        assert any("说明文档.txt" in item for item in scan_scope._secret_scan(root))
        subprocess.run(["git", "add", "说明文档.txt"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "sample"], cwd=root, check=True, capture_output=True, env=env)
        errors = scan_scope._secret_scan(root)
        assert any("说明文档.txt" in item for item in errors), errors


if __name__ == "__main__":
    test_tracked_files_include_unicode_names()
    test_secret_in_chinese_filename_is_reported()
    print("scan_scope_unicode_ok")
