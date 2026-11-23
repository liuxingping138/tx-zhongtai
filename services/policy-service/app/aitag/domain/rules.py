"""政策 AI 打标的纯规则：源数据怎么喂给模型，模型的回答怎么落到基础标签。"""

from __future__ import annotations

import re
from typing import Any

from app.common.interpret_fields import SOURCE_ID
from app.common.policy_text import TITLE_SCRIPT_NOTE, _text, clean_content, page_text, policy_title
from app.policy.domain.fields import (
    AI_NOTE_INTERPRET_FAILED,
    AI_NOTE_OPPORTUNITY_FAILED,
    AI_NOTE_TYPE_EMPTY,
    AI_NOTE_TYPE_FAILED,
    AI_NOTE_TYPE_UNKNOWN,
    TYPE_NOTES,
)

INFORMATIZATION = "信息化建设类"
TYPE_FIELD = "政策类型名称"
TYPE_FIELDS = ("政策类型", "政策类型名称")
IS_POLICY_FIELD = "是否政策"
IGNORED_AI_OUTPUT_FIELDS = ("是否信息化政策", "信息化标签")
DEFAULT_AI_OUTPUT_FIELDS = ("是否政策", "判定简因")
_BLANK_OUTPUTS = {"-", "—", "无", "none", "null"}
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
PROMPT_COLUMNS = ("政策标题", "政策正文", "省份", "地市", "出台时间", "发文部门", "政策层级")
__all__ = ["SOURCE_ID", "TITLE_SCRIPT_NOTE", "clean_content", "page_text", "policy_title"]


def prompt_row(row: dict[str, Any], content: str | None, max_chars: int) -> dict[str, str]:
    return {
        SOURCE_ID: _text(row.get("content_id")),
        "政策标题": policy_title(row.get("name"))[0],
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


def _need_interpret(types: list[str], ai_outputs: dict[str, str] | None) -> str:
    """是否进入政策解读：「是否政策 = 否」不解读；否则只看政策类型是否包含「信息化建设类」。"""

    if ai_outputs and ai_outputs.get(IS_POLICY_FIELD) == "否":
        return "否"
    return "是" if INFORMATIZATION in types else "否"


def extract_ai_outputs(result: dict[str, Any]) -> dict[str, str]:
    """取出模型按模板输出的所有扩展字段（源ID、政策类型及已移除的旧信息化字段不重复存）。"""

    if result.get("error"):
        return {}
    out: dict[str, str] = {}
    for item in result.get("items") or []:
        if not isinstance(item, dict):
            continue
        for key, raw in item.items():
            if not isinstance(key, str) or key in (SOURCE_ID, *TYPE_FIELDS, *IGNORED_AI_OUTPUT_FIELDS):
                continue
            val = _text(raw)
            if val.lower() in _BLANK_OUTPUTS:
                val = ""
            if key not in out or (val and not out[key]):
                out[key] = val
    return out


def base_tag_values(
    row: dict[str, Any], types: list[str], remark: str, ai_outputs: dict[str, str] | None = None
) -> dict[str, str]:
    """基础标签的业务字段。穿透词三列来自别的流程，打标不填。"""

    title, from_script = policy_title(row.get("name"))
    if from_script:
        remark = NOTE_SEP.join(part for part in (remark, TITLE_SCRIPT_NOTE) if part)
    return {
        "policy_name": title,
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
        "need_interpret": _need_interpret(types, ai_outputs),
        "remark": remark,
    }


def tagging_outcome(result: dict[str, Any], known: list[str]) -> tuple[list[str], str]:
    """一行的结果 -> (类型, 备注)。失败、没对上码表都写进备注，页面上能筛出来人工处理。"""

    if result.get("error"):
        return [], f"{AI_NOTE_TYPE_FAILED}：{str(result['error'])[:200]}"
    items = [item for item in (result.get("items") or []) if isinstance(item, dict)]
    answers = [str(item.get("政策类型") or item.get(TYPE_FIELD) or "") for item in items]
    types, unknown = parse_policy_types("、".join(answers), known)
    if unknown:
        return types, f"{AI_NOTE_TYPE_UNKNOWN}：{'、'.join(unknown)}"
    if not types:
        if any(_text(item.get(IS_POLICY_FIELD)) == "否" for item in items):
            return [], ""
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


# 基础标签里由人维护、打标不碰的列。
MANUAL_FIELDS = ("is_penetrate", "penetrate_words", "penetrate_score")
AI_NOTES = (
    AI_NOTE_TYPE_FAILED,
    AI_NOTE_TYPE_UNKNOWN,
    AI_NOTE_TYPE_EMPTY,
    AI_NOTE_INTERPRET_FAILED,
    AI_NOTE_OPPORTUNITY_FAILED,
    TITLE_SCRIPT_NOTE,
)
DUPLICATE_NOTE = "重新判断后内容和另一条基础标签相同，未重复写入"
COPY_SKIPPED = "和已有基础标签内容相同"
MISSING_NOTE = "源库里已经找不到这条政策，没有重新判断类型"


def redoes_downstream(existing: Any, values: dict[str, str]) -> bool:
    """重新判断类型后解读、市场机会要不要重做：类型或「是否解读」变了才重做（用户定的，解读最贵）。"""

    return (existing.policy_types, existing.need_interpret) != (values["policy_types"], values["need_interpret"])


def keep_manual_edits(values: dict[str, str], existing: Any) -> dict[str, str]:
    """重新判断类型覆盖的是源库字段和类型：人填的穿透三列照旧，备注里人写的几段留着，只换掉 AI 写的几段。

    类型没变时解读、市场机会不重做，它们上次的失败说明还算数，要留着：去掉的话这条显示「已完成」、
    解读表里却一行都没有，「解读失败」筛不出来、待办里也没有，永远不会再做。
    """

    kept = dict(values)
    for field in MANUAL_FIELDS:
        kept[field] = getattr(existing, field) or ""
    stale = AI_NOTES if redoes_downstream(existing, values) else (*TYPE_NOTES, TITLE_SCRIPT_NOTE)
    # 上次重判留下的「和另一条相同」「源库找不到」也是那时的说明，这次判成功了就该去掉。
    old = drop_notes(existing.remark, (*stale, DUPLICATE_NOTE, MISSING_NOTE))
    kept["remark"] = NOTE_SEP.join(part for part in (values["remark"], old) if part)
    return kept


def note_duplicate(remark: str, source_id: str) -> str:
    """这次的结果不写了，上次类型判断的失败说明也就过时了，一起去掉。类型、解读都没动，解读和市场机会的失败说明留着。

    备注带上本条的源政策ID：同一网页采了三条以上时，好几条重判后都和同一条相同，备注一样的话
    它们彼此又撞内容哈希，整批回滚、队列清不掉，每次执行都先花钱再失败。源政策ID 一条一个，撞不上。
    """

    note = f"{DUPLICATE_NOTE}（源政策ID {source_id}）"
    return NOTE_SEP.join(part for part in (note, drop_notes(remark, (DUPLICATE_NOTE, *TYPE_NOTES))) if part)
