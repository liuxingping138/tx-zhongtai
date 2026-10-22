"""政策 AI 打标的纯规则：源数据怎么喂给模型，模型的回答怎么落到基础标签。"""

from __future__ import annotations

import re
from typing import Any

INFORMATIZATION = "信息化建设类"
TYPE_FIELD = "政策类型名称"
TYPES_MAX = 5
# 模型偶尔用逗号、分号、斜杠代替顿号，都按分隔符处理。
_TYPE_SEPARATORS = re.compile(r"[、,，;；/|｜\s]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")
_SPACES = re.compile(r"[ \t　\xa0]+")
# 模型看到的列名，模板里用 @【列名】引用。改名会让已上线的模板引用落空。
SOURCE_ID = "源ID"
PROMPT_COLUMNS = ("政策标题", "政策正文", "省份", "地市", "出台时间", "发文部门", "政策层级")


def clean_content(text: str | None, max_chars: int) -> str:
    """正文是整页抓下来的文字：压掉连续空白和空行。

    max_chars 为 0 时全文照传；否则截到上限，截断处标明，免得模型以为原文就到这。
    """

    value = _BLANK_LINES.sub("\n", _SPACES.sub(" ", (text or "").replace("\r", "\n"))).strip()
    if max_chars <= 0 or len(value) <= max_chars:
        return value
    return value[:max_chars] + "……（正文过长，以下省略）"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def prompt_row(row: dict[str, Any], content: str | None, max_chars: int) -> dict[str, str]:
    return {
        SOURCE_ID: _text(row.get("content_id")),
        "政策标题": _text(row.get("name")),
        "政策正文": clean_content(content, max_chars),
        "省份": _text(row.get("prov_name")),
        "地市": _text(row.get("city_name")),
        "出台时间": _text(row.get("introduced_date")),
        "发文部门": _text(row.get("introduced_department")),
        "政策层级": _text(row.get("level")),
    }


def parse_policy_types(answer: str, known: list[str]) -> tuple[list[str], list[str]]:
    """拆出码表里有的类型（按回答顺序，去重，最多 5 个）和码表里没有的写法。

    模板里的码表曾不带「类」字，模型可能还按旧写法回答：「信息化建设」补成「信息化建设类」后能对上就算对上。
    """

    names = set(known)
    matched: list[str] = []
    unknown: list[str] = []
    for part in _TYPE_SEPARATORS.split(answer or ""):
        name = part.strip().strip("“”\"'")
        if not name or name in {"-", "无"}:
            continue
        resolved = name if name in names else f"{name}类" if f"{name}类" in names else ""
        if not resolved:
            unknown.append(name)
        elif resolved not in matched:
            matched.append(resolved)
    return matched[:TYPES_MAX], unknown


def base_tag_values(row: dict[str, Any], types: list[str], remark: str) -> dict[str, str]:
    """基础标签的业务字段。穿透词三列来自别的流程，打标不填。"""

    return {
        "policy_name": _text(row.get("name")),
        "issuing_dept": _text(row.get("introduced_department"))[:255],
        "issuer_industry": _text(row.get("department_industry"))[:255],
        "policy_level": _text(row.get("level"))[:64],
        "province_code": _text(row.get("prov_id"))[:16],
        "province_name": _text(row.get("prov_name"))[:64],
        "city_code": _text(row.get("city_id"))[:16],
        "city_name": _text(row.get("city_name"))[:64],
        "issued_at": _text(row.get("introduced_date"))[:64],
        "policy_types": "、".join(types),
        "source_url": _text(row.get("original_link")),
        "is_penetrate": "",
        "penetrate_words": "",
        "penetrate_score": "",
        # 只有信息化建设类往下做政策解读。
        "need_interpret": "是" if INFORMATIZATION in types else "否",
        "remark": remark,
    }


def tagging_outcome(result: dict[str, Any], known: list[str]) -> tuple[list[str], str]:
    """一行的结果 -> (类型, 备注)。失败、没对上码表都写进备注，页面上能筛出来人工处理。"""

    if result.get("error"):
        return [], f"AI 类型判断失败：{str(result['error'])[:200]}"
    answers = [str(item.get(TYPE_FIELD) or "") for item in result.get("items") or []]
    types, unknown = parse_policy_types("、".join(answers), known)
    if unknown:
        return types, f"AI 返回的类型不在码表里：{'、'.join(unknown)}"
    if not types:
        return [], "AI 没有判断出政策类型"
    return types, ""


def resume_point(results: list[dict[str, Any]], not_run: str) -> int:
    """下次从哪一行接着读：第一条没执行（费用到上限、任务停止）的行之前都算处理过。返回已处理的行数。"""

    for index, result in enumerate(results):
        if str(result.get("error") or "").startswith(not_run):
            return index
    return len(results)
