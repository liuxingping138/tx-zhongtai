"""模板附件与批量结果的磁盘布局。路径只由 32 位十六进制 ID 拼出，用户给的文件名只存库用于展示。

<data_dir>/prompts/<模板ID>/source.xlsx   模板 Excel
<data_dir>/prompts/<模板ID>/code.txt      码表
<data_dir>/runs/<任务ID>/...              批量产物（见 RUN_FILES）；输入快照是 source.xlsx，流水线任务是 rows.json，
                                         逐行结果预览另存一份 input.jsonl
<data_dir>/releases/<版本ID>/code.txt    上线时冻结的上传码表（用系统码表的版本没有这个文件）
"""

from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path

from app.core.config import get_settings

ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")

PROMPT_FILES = {"excel": "source.xlsx", "code": "code.txt"}
# 流水线任务的输入：调用方传来的行原样存 JSON。政策正文可能十几万字，超过 Excel 单元格上限，不能存成 xlsx。
ROWS_FILE = "rows.json"
# 输入快照按行另存的副本：逐行结果预览只看前几十行，不用每次把整个 Excel 解析一遍。第一次预览时生成。
INPUT_LINES_FILE = "input.jsonl"
# 下载名用中文，落盘名固定，避免中文路径和用户文件名带来的路径问题。
RUN_FILES = {
    "result": ("ask_result.xlsx", "结果.xlsx"),
    "raw": ("temp.csv", "原始返回.csv"),
    "log": ("run.log", "运行日志.log"),
    "failed": ("failed.csv", "失败清单.csv"),
}


def _checked(identifier: str) -> str:
    if not ID_PATTERN.fullmatch(identifier):
        raise ValueError("非法 ID")
    return identifier


def data_dir() -> Path:
    return get_settings().data_dir


def prompt_dir(prompt_id: str) -> Path:
    return data_dir() / "prompts" / _checked(prompt_id)


def prompt_file(prompt_id: str, kind: str) -> Path:
    return prompt_dir(prompt_id) / PROMPT_FILES[kind]


def run_dir(run_id: str) -> Path:
    return data_dir() / "runs" / _checked(run_id)


def release_dir(release_id: str) -> Path:
    return data_dir() / "releases" / _checked(release_id)


def release_code_file(release_id: str) -> Path:
    return release_dir(release_id) / PROMPT_FILES["code"]


def run_file(run_id: str, kind: str) -> Path:
    return run_dir(run_id) / RUN_FILES[kind][0]


def write_atomic(path: Path, content: bytes) -> None:
    """先写临时文件再改名：批量 worker 同时读这个文件时，读到的要么是旧的、要么是完整的新的。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    # 临时文件名各不相同：两个请求同时写同一个文件（如同时第一次打开预览）时不会写进同一个临时文件。
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def remove_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
