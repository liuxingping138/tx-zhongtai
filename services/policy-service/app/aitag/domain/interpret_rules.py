"""政策解读、市场机会两步的纯规则：模型回答的字段怎么落到解读表，市场机会怎么对回各行。"""

from __future__ import annotations

import re
from typing import Any

from app.common.interpret_fields import (
    ANSWER_FIELDS,
    EXTRA_INTERPRET_ALIASES,
    KNOWN_INTERPRET_KEYS,
    SOURCE_ID,
)

__all__ = [
    "ANSWER_FIELDS",
    "EXTRA_INTERPRET_ALIASES",
    "KNOWN_INTERPRET_KEYS",
    "SOURCE_ID",
]
# 和库里列宽一致，超出的截断，免得一条超长回答让整批写入失败。
_WIDTHS = {
    "industry_l1": 128,
    "industry_l2": 128,
    "industry_l3": 128,
    "scenario_l1_name": 255,
    "scenario_l2_name": 255,
    "scenario_l3_name": 255,
    "opportunity_type": 64,
    "has_subsidy": 32,
    "info_level": 32,
    "is_new_scenario": 32,
    "new_scenario_level": 64,
}
LEVEL_FIELDS = ("industry_l1", "industry_l2", "industry_l3", "scenario_l1_name", "scenario_l2_name", "scenario_l3_name")
_BLANKS = {"-", "—", "无", "none", "null"}
UID_MAX = 64


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in _BLANKS else text


# 系统码表把层级连写成「交通行业 > 交通运输业 > 多式联运」（见 codebook 的 code_tables）。码表名称里没有「>」。
_LEVEL_SEP = re.compile(r"\s*[>＞]\s*")
_LEVEL_GROUPS = (LEVEL_FIELDS[:3], LEVEL_FIELDS[3:])
# 模板让模型「标识新增的是哪一级场景」，它有时直接在名称后面写「（新增）」。哪级是新的看「新增场景级别」，
# 名称里不留标记，否则同步进码表后码表里就多了带「（新增）」的场景。
_NEW_MARK = re.compile(r"\s*[（(【\[]\s*新增\s*[）)】\]]\s*")


def _split_levels(values: dict[str, str]) -> None:
    """模型偶尔把码表里的整条路径原样填进一个字段。按层级拆回一二三级，不然名称对不上码表、查不到编码。

    同一组（行业或场景）里取段数最多的那条路径，从第一级往下填；路径没覆盖到的级别保留模型自己填的值。
    """

    for fields in _LEVEL_GROUPS:
        paths = [_LEVEL_SEP.split(values[field]) for field in fields if _LEVEL_SEP.search(values[field])]
        if not paths:
            continue
        parts = [part for part in max(paths, key=len) if part][: len(fields)]
        for index, field in enumerate(fields):
            if index < len(parts):
                values[field] = parts[index]
            elif _LEVEL_SEP.search(values[field]):
                values[field] = ""


def interpretation_values(item: dict[str, Any]) -> dict[str, str]:
    values = dict.fromkeys(set(ANSWER_FIELDS.values()), "")
    for answer_name, column in (*ANSWER_FIELDS.items(), *EXTRA_INTERPRET_ALIASES.items()):
        if column not in values:
            continue
        text = _clean(item.get(answer_name))
        if text and not values[column]:
            values[column] = text
    _split_levels(values)
    for field in LEVEL_FIELDS:
        values[field] = _NEW_MARK.sub("", values[field]).strip()
    for column, width in _WIDTHS.items():
        values[column] = values[column][:width]
    # 模型偶尔答「是的」「新增」，统一成表里的是 / 否。
    values["is_new_scenario"] = "是" if values["is_new_scenario"].startswith(("是", "新增")) else "否"
    return values


def extract_ai_outputs(item: dict[str, Any]) -> dict[str, str]:
    """取出解读或市场机会模板输出中、不在固定列映射里的新增动态字段。"""

    out: dict[str, str] = {}
    if not isinstance(item, dict):
        return out
    for key, raw in item.items():
        if not isinstance(key, str) or key in KNOWN_INTERPRET_KEYS:
            continue
        val = _clean(raw)
        if key not in out or (val and not out[key]):
            out[key] = val
    return out


def scenario_names(values: dict[str, str]) -> tuple[str, ...]:
    return tuple(values[field] for field in LEVEL_FIELDS)


def relation_key(content_id: str, values: dict[str, str]) -> str:
    """AI 行的关联主键：政策 + 行业场景 + 机会类型。新增场景还没有编码，用六级名称代替，同一条政策里不会撞。"""

    code = values.get("industry_scenario_code") or "新:" + "/".join(scenario_names(values))
    return f"{content_id[:UID_MAX]}{code}{values.get('opportunity_type', '')}"


# 市场机会这一步多给模板的一列：这条政策解读出的「一级行业/一级场景」，一行一个。
SCENES_COLUMN = "行业场景"


def opportunity_prompt_row(base: dict[str, str], rows: list[dict[str, str]]) -> dict[str, str]:
    """市场机会这一步额外带上解读出的「一级行业/一级场景」，模板可以用 @【行业场景】引用，按它逐个写机会。"""

    pairs = list(dict.fromkeys(f"{row['industry_l1']}/{row['scenario_l1_name']}" for row in rows))
    return {**base, SCENES_COLUMN: "\n".join(pairs)}


def match_opportunities(items: list[dict[str, Any]], rows: list[dict[str, str]]) -> dict[int, str]:
    """把一条政策的市场机会对回它的解读行：按一级行业 + 一级场景，对不上退到一级行业；
    模型只给了一段又哪都对不上时，整条政策的行都用它。返回 {行下标: 机会文本}。"""

    matched: dict[int, list[str]] = {}
    texts = [(item, _clean(item.get("市场机会") or item.get("政策市场机会"))) for item in items]
    texts = [(item, text) for item, text in texts if text]
    for item, text in texts:
        # 「一级行业 / 一级场景」是解读那一步的写法，业务人员照着写市场机会模板也很常见，两种都认。
        industry = _clean(item.get("行业") or item.get("一级行业"))
        scene = _clean(item.get("场景") or item.get("一级场景"))
        hits = [i for i, row in enumerate(rows) if row["industry_l1"] == industry and row["scenario_l1_name"] == scene]
        hits = hits or [i for i, row in enumerate(rows) if industry and row["industry_l1"] == industry]
        if not hits and len(texts) == 1:
            hits = list(range(len(rows)))
        for index in hits:
            matched.setdefault(index, []).append(text)
    return {index: "\n\n".join(parts) for index, parts in matched.items()}


def base_prompt_row(tag: Any, content: str) -> dict[str, str]:
    """后两步从基础标签取政策信息，正文按需从源库重读。列名和第一步一致，同一套模板变量。"""

    return {
        SOURCE_ID: str(tag.source_content_id),
        "政策标题": tag.policy_name,
        "政策正文": content,
        "省份": tag.province_name,
        "地市": tag.city_name,
        "出台时间": tag.issued_at,
        "发文部门": tag.issuing_dept,
        "政策层级": tag.policy_level,
    }
