"""政策 AI 打标的纯规则：源数据怎么喂给模型，模型的回答怎么落到基础标签。"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

from app.policy.domain.fields import (
    AI_NOTE_INTERPRET_FAILED,
    AI_NOTE_OPPORTUNITY_FAILED,
    AI_NOTE_TYPE_EMPTY,
    AI_NOTE_TYPE_FAILED,
    AI_NOTE_TYPE_UNKNOWN,
)

INFORMATIZATION = "信息化建设类"
TYPE_FIELD = "政策类型名称"
# 解读、市场机会失败时追加到基础标签备注里的前缀；重新打标时据此清掉旧的失败说明，列表也按它筛。
INTERPRET_FAILED = AI_NOTE_INTERPRET_FAILED
OPPORTUNITY_FAILED = AI_NOTE_OPPORTUNITY_FAILED
NOTE_SEP = "；"
TYPES_MAX = 5
# 模型偶尔用逗号、分号、斜杠代替顿号，都按分隔符处理。
_TYPE_SEPARATORS = re.compile(r"[、,，;；/|｜\s]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")
_SPACES = re.compile(r"[ \t　\xa0]+")
# 模型看到的列名，模板里用 @【列名】引用。改名会让已上线的模板引用落空。
SOURCE_ID = "源ID"
PROMPT_COLUMNS = ("政策标题", "政策正文", "省份", "地市", "出台时间", "发文部门", "政策层级")


# 源库的「正文」是整页网页源码（实测 60 条全是，文字只占 6% 左右，其余是标签、样式和脚本）。
_HTML_START = re.compile(r"<\s*(?:!doctype|html|head|body|div|p|span|br|table|meta|script)\b", re.IGNORECASE)
# 这些标签里的内容不是给人看的。
_HIDDEN_TAGS = {"script", "style", "head", "noscript", "template", "svg", "iframe"}
# 块级标签前后断行，保留段落；行内标签（span、a、strong…）不断，免得把一句话拆成好几行。
_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "header", "footer",
    "h1", "h2", "h3", "h4", "h5", "h6", "dd", "dt", "dl", "blockquote", "pre", "hr",
}  # fmt: skip


class _PageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _HIDDEN_TAGS:
            self._hidden += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _HIDDEN_TAGS:
            self._hidden = max(0, self._hidden - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._hidden:
            self.parts.append(data)


def page_text(text: str) -> str:
    """网页源码 -> 看得见的文字（去掉脚本、样式、网页头，块级标签处断行）。不像网页的原样返回。"""

    if not _HTML_START.search(text[:5000]):
        return text
    parser = _PageText()
    parser.feed(text)
    parser.close()
    return "".join(parser.parts)


def clean_content(text: str | None, max_chars: int) -> str:
    """正文发给模型前的整理：网页源码先提取成文字，再压掉连续空白和空行。

    max_chars 为 0 时全文照传；否则截到上限，截断处标明，免得模型以为原文就到这。
    """

    value = page_text((text or "").replace("\r", "\n"))
    lines = (line.strip() for line in _SPACES.sub(" ", value).split("\n"))
    value = _BLANK_LINES.sub("\n", "\n".join(line for line in lines if line)).strip()
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
        return [], f"{AI_NOTE_TYPE_FAILED}：{str(result['error'])[:200]}"
    answers = [str(item.get(TYPE_FIELD) or "") for item in result.get("items") or []]
    types, unknown = parse_policy_types("、".join(answers), known)
    if unknown:
        return types, f"{AI_NOTE_TYPE_UNKNOWN}：{'、'.join(unknown)}"
    if not types:
        return [], AI_NOTE_TYPE_EMPTY
    return types, ""


def resume_point(results: list[dict[str, Any]], not_run: str) -> int:
    """下次从哪一行接着读：第一条没执行（费用到上限、任务停止）的行之前都算处理过。返回已处理的行数。"""

    for index, result in enumerate(results):
        if str(result.get("error") or "").startswith(not_run):
            return index
    return len(results)


def drop_notes(remark: str, prefixes: tuple[str, ...]) -> str:
    """去掉备注里以这些前缀开头的几段（备注各段用「；」连接），其余原样保留。"""

    return NOTE_SEP.join(part for part in (remark or "").split(NOTE_SEP) if part and not part.startswith(prefixes))
