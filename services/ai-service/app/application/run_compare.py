"""样本试跑和上一次对比：同一份测试样本按行号一一对上，看这次改提示词修好了哪些、弄坏了哪些、哪些字段值变了。

只比两次都跑到了的行；测试样本换过就没法逐行对上，由调用方先判断。同步文件操作，调用方放线程池。
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.core import storage

PROBLEMS = ("failed", "format")
CHANGES = ("fixed", "broke", "changed")
_KEPT = ("status", "items", "error", "answer")
# 超过这么多字的值算说明文字（打标理由、解读概述）：真模型每次措辞都不一样，算进「字段变了」会把标签的真变化淹没。
PROSE_CHARS = 40


def is_prose(*values: str) -> bool:
    return any(len(value) > PROSE_CHARS for value in values)


def labels_differ(items: list[dict[str, str]], previous: list[dict[str, str]]) -> bool:
    """两次解析结果是不是真变了：条数不同算变；同一条里只比短的标签类字段，两边都是说明文字的不比。"""

    if len(items) != len(previous):
        return True
    for now, old in zip(items, previous, strict=True):
        for field in now.keys() | old.keys():
            a, b = now.get(field, ""), old.get(field, "")
            if a != b and not is_prose(a, b):
                return True
    return False


def _digest(run_id: str) -> str:
    path = storage.run_dir(run_id) / storage.PROMPT_FILES["excel"]
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def same_input(run_id: str, other_id: str) -> bool:
    """两次试跑用的是不是同一份测试样本：按发起时复制进任务目录的那份比内容，改名、重传同一份都算同一份。"""

    first = _digest(run_id)
    return bool(first) and first == _digest(other_id)


def change_of(current: dict[str, Any], previous: dict[str, Any] | None) -> str:
    """fixed：上次有问题这次成功；broke：上次成功这次有问题；changed：两次都成功但标签类字段不同（说明文字措辞变了不算）。"""

    if previous is None or "pending" in (current["status"], previous["status"]):
        return ""
    now_bad, was_bad = current["status"] in PROBLEMS, previous["status"] in PROBLEMS
    if was_bad and not now_bad:
        return "fixed"
    if now_bad and not was_bad:
        return "broke"
    if not now_bad and labels_differ(current["items"], previous["items"]):
        return "changed"
    return ""


def compare(rows: dict[str, Any], previous_rows: dict[str, Any]) -> dict[str, int]:
    """给 rows 的每一行挂上上一次的结果（previous）和变化（change），返回各类行数；same 是两次都跑到、没变化的。"""

    before = {item["row"]: item for item in previous_rows["items"]}
    counts = dict.fromkeys((*CHANGES, "same"), 0)
    for item in rows["items"]:
        old = before.get(item["row"])
        item["previous"] = {key: old[key] for key in _KEPT} if old else None
        item["change"] = change_of(item, old)
        if old is not None and "pending" not in (item["status"], old["status"]):
            counts[item["change"] or "same"] += 1
    return counts
