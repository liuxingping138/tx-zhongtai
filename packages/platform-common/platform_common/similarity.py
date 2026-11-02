"""名称的字面相似度：AI 新写的场景说法和已有的像不像（码表比对、新增场景之间比对都用它）。

字符二元组的重合比例，一个完整包含另一个时至少 0.5。只看字面：意思近、说法不同的找不出来，那种靠 AI 判断。
"""

from __future__ import annotations

import re

_NOISE = re.compile(r"[\s（）()【】\[\]、，,·/\-—]")
# 短于这个长度的名称不算「包含」：「智慧」「平台」这类词几乎被所有场景名包含。
MIN_CONTAIN = 3
HIGH = 0.6
MEDIUM = 0.35
LEVEL_HIGH = "高"
LEVEL_MEDIUM = "中"
LEVEL_NONE = "无"


def _clean(name: str) -> str:
    return _NOISE.sub("", name)


def _grams(text: str) -> set[str]:
    return {text[i : i + 2] for i in range(len(text) - 1)} or {text}


def similarity(a: str, b: str) -> float:
    """两个名称的字面相似度，0 到 1。"""

    a, b = _clean(a), _clean(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ga, gb = _grams(a), _grams(b)
    score = len(ga & gb) / len(ga | gb)
    short, long = sorted((a, b), key=len)
    if len(short) >= MIN_CONTAIN and short in long:
        score = max(score, 0.5 + 0.5 * len(short) / len(long))
    return round(score, 2)


def similarity_level(score: float) -> str:
    if score >= HIGH:
        return LEVEL_HIGH
    if score >= MEDIUM:
        return LEVEL_MEDIUM
    return LEVEL_NONE
