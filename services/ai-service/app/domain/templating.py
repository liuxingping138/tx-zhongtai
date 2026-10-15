"""提示词变量替换与模型返回解析，规则与旧系统 batch_runner 一致。

模板里写 @【列名】引用 Excel 当前行的值，@【上传码表】替换为整段码表文本；
模型按要求返回 [{字段: 值}, ...]，按「新增输出字段」逐条抽取，一个提问可以对应多条结果。
"""

from __future__ import annotations

import json
import re

CODE_TABLE_FIELD = "上传码表"
_VAR_RE = re.compile(r"@【([^】]+)】")
_JSON_START = re.compile(r"[\[{]")
_MYID_BASE = 1_000_000


def build_myid(index: int) -> str:
    """按 Excel 数据行序号生成行号：a1000001 起，与旧系统产物一致，便于和历史结果对照。"""

    return f"a{index + 1 + _MYID_BASE}"


def split_fields(output_fields: str) -> list[str]:
    return [item.strip() for item in (output_fields or "").split("|") if item.strip()]


def template_variables(content: str) -> list[str]:
    return [match.strip() for match in _VAR_RE.findall(content or "")]


def fill_template(content: str, row: dict[str, str], code_text: str = "") -> str:
    """Excel 里没有的列保留 @【列名】原样，方便一眼看出写错了列名。"""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key == CODE_TABLE_FIELD:
            return code_text
        if key in row:
            return row[key]
        return match.group(0)

    return _VAR_RE.sub(replace, content or "")


def _clean_json(group: str) -> str:
    # 模型常输出 LaTeX 或未转义的反斜杠：多重反斜杠降一级，非法单反斜杠补成合法转义。
    group = group.replace("\\\\\\\\", "\\\\")
    return re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r"\\\\", group)


def _json_candidates(text: str) -> list[object]:
    """从任意位置起逐段尝试解码 JSON，模型在前后加说明、代码块围栏或思考过程都不影响。"""

    decoder = json.JSONDecoder()
    found: list[object] = []
    for source in (text, _clean_json(text)):
        position = 0
        while match := _JSON_START.search(source, position):
            try:
                value, end = decoder.raw_decode(source, match.start())
            except json.JSONDecodeError:
                position = match.start() + 1
                continue
            found.append(value)
            position = end
        if found:
            break
    return found


def _entries(value: object) -> list[dict[str, object]]:
    if isinstance(value, dict):
        return [value]
    return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []


def parse_fields(text: str, fields: list[str]) -> list[dict[str, str]] | None:
    """解析不出任何一个输出字段时返回 None，由调用方判定为「返回格式不对」。

    优先取第一段含输出字段的 [{...}]；模型只回了单个 {...} 也接受，当作一条。
    """

    if not text or not fields:
        return None
    for value in _json_candidates(text):
        entries = [entry for entry in _entries(value) if any(name in entry for name in fields)]
        if entries:
            return [
                {name: "" if entry.get(name) is None else str(entry.get(name)) for name in fields} for entry in entries
            ]
    return None


def extract_fields(text: str, fields: list[str]) -> list[dict[str, str]]:
    """解析不到时返回一条全空的结果，保证这一行仍出现在结果表里。"""

    return parse_fields(text, fields) or [dict.fromkeys(fields, "")]
