"""源库政策 HTML 转纯文本与网页脚本标题解析，政策正文展示与 AI 打标共用。"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

_BLANK_LINES = re.compile(r"\n\s*\n+")
_SPACES = re.compile(r"[ \t　\xa0]+")

_HTML_START = re.compile(r"<\s*(?:!doctype|html|head|body|div|p|span|br|table|meta|script)\b", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]*>")
_HIDDEN_TAGS = {"script", "style", "head", "noscript", "template", "svg", "iframe"}
_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "header", "footer",
    "h1", "h2", "h3", "h4", "h5", "h6", "dd", "dt", "dl", "blockquote", "pre", "hr",
}  # fmt: skip

_CHROME_TAGS = {"nav", "header", "footer", "aside"}
_CHROME_WORDS = {"header", "footer", "foot", "nav", "navbar", "menu", "submenu", "topbar", "breadcrumb", "crumb"}
_NEGATIONS = {"no", "not", "non", "without"}
_CONTENT_WORDS = {"article", "content", "detail", "text", "body", "doc", "zw", "news", "info", "title", "con"}
_NAME_PARTS = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")

_SCRIPT_TITLE = re.compile(r"^document\.write\s*\(")
_STRING_LITERAL = re.compile(r"\"((?:[^\"\\]|\\.)*)\"|'((?:[^'\\]|\\.)*)'")
_TAG = re.compile(r"<[^>]*>")
TITLE_SCRIPT_NOTE = "标题原文是网页脚本，已取出其中的文字"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _is_chrome(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
    if tag in _CHROME_TAGS:
        return True
    for key, value in attrs:
        for name in (value or "").split() if key in ("class", "id") else ():
            parts = [part.lower() for part in _NAME_PARTS.findall(name)]
            negated = parts and parts[0] in _NEGATIONS
            if parts and not negated and _CHROME_WORDS.intersection(parts) and not _CONTENT_WORDS.intersection(parts):
                return True
    return False


class _PageText(HTMLParser):
    def __init__(self, *, skip_chrome: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_open: list[str] = []
        self._skip_chrome = skip_chrome
        self._chrome = ""
        self._chrome_depth = 0

    @property
    def _hidden(self) -> bool:
        return bool(self._hidden_open)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if "head" in self._hidden_open and (tag == "body" or tag in _BLOCK_TAGS):
            self._hidden_open = [name for name in self._hidden_open if name != "head"]
        if self._chrome:
            if tag == self._chrome:
                self._chrome_depth += 1
        elif tag in _HIDDEN_TAGS:
            self._hidden_open.append(tag)
        elif self._skip_chrome and not self._hidden and _is_chrome(tag, attrs):
            self._chrome, self._chrome_depth = tag, 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK_TAGS and not self._chrome:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._chrome:
            if tag == self._chrome:
                self._chrome_depth -= 1
                if not self._chrome_depth:
                    self._chrome = ""
                    self.parts.append("\n")
        elif tag in _HIDDEN_TAGS:
            if tag in self._hidden_open:
                index = len(self._hidden_open) - 1 - self._hidden_open[::-1].index(tag)
                del self._hidden_open[index:]
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._hidden and not self._chrome:
            self.parts.append(data)

    @property
    def chrome_open(self) -> bool:
        return bool(self._chrome)


def _visible_text(text: str, *, skip_chrome: bool) -> str | None:
    parser = _PageText(skip_chrome=skip_chrome)
    parser.feed(text)
    parser.close()
    return None if parser.chrome_open else "".join(parser.parts)


def _keeps_body(full: str, body: str) -> bool:
    longest = max(("".join(line.split()) for line in full.split("\n")), key=len, default="")
    return longest in "".join(body.split())


def page_text(text: str) -> str:
    """网页源码 -> 看得见的文字（去掉脚本、样式、网页头、导航和页脚，块级标签处断行）。"""

    if not _HTML_START.search(text[:5000]):
        return text
    full = _visible_text(text, skip_chrome=False) or ""
    if not full.strip():
        return _TAGS.sub(" ", text)
    body = _visible_text(text, skip_chrome=True)
    return body if body is not None and _keeps_body(full, body) else full


def clean_content(text: str | None, max_chars: int) -> str:
    """正文整理：网页源码提取纯文字并压缩空白；max_chars 为 0 时全文照传。"""

    value = page_text((text or "").replace("\r", "\n"))
    lines = (line.strip() for line in _SPACES.sub(" ", value).split("\n"))
    value = _BLANK_LINES.sub("\n", "\n".join(line for line in lines if line)).strip()
    if max_chars <= 0 or len(value) <= max_chars:
        return value
    return value[:max_chars] + "……（正文过长，以下省略）"


def policy_title(raw: Any) -> tuple[str, bool]:
    """源库的政策标题 -> (标题, 是否从脚本里取的)。"""

    title = _text(raw)
    if not _SCRIPT_TITLE.match(title):
        return title, False
    texts = (_TAG.sub("", first or second).strip() for first, second in _STRING_LITERAL.findall(title))
    best = max(texts, key=len, default="")
    return (best, True) if best else (title, False)
