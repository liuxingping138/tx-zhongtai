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


# 市场机会这一步给模板的行业场景列：模式 A 按（一级行业、一级场景）逐组展开，同时保留「行业场景」兼容旧模板。
INDUSTRY_L1_COLUMN = "一级行业"
SCENARIO_L1_COLUMN = "一级场景"
SCENES_COLUMN = "行业场景"


def opportunity_prompt_rows(
    base: dict[str, str], rows: list[dict[str, str]]
) -> list[tuple[tuple[str, str], dict[str, str]]]:
    """模式 A：按解读出的（一级行业、一级场景）去重逐组展开，每组生成一条市场机会输入行。
    行业或场景是空的组不问：拿空名称问模型白花钱，也写不回哪一行。"""

    pairs = list(
        dict.fromkeys(
            (row["industry_l1"].strip(), row["scenario_l1_name"].strip())
            for row in rows
            if row["industry_l1"].strip() and row["scenario_l1_name"].strip()
        )
    )
    return [
        (
            (industry, scene),
            {
                **base,
                INDUSTRY_L1_COLUMN: industry,
                SCENARIO_L1_COLUMN: scene,
                SCENES_COLUMN: f"{industry}/{scene}",
            },
        )
        for industry, scene in pairs
    ]


def _labels(item: dict[str, Any]) -> tuple[str, str]:
    # 「一级行业 / 一级场景」是解读那一步的写法，业务人员照着写市场机会模板也很常见，两种都认。
    return _clean(item.get("行业") or item.get("一级行业")), _clean(item.get("场景") or item.get("一级场景"))


def extract_opportunity_text(items: list[dict[str, Any]], industry: str, scene: str) -> str:
    """从单组（一级行业、一级场景）的模型输出里取市场机会文本，回填到这一组的解读行。

    一次只问一组，所以：标了行业场景、和这组对得上的优先；没标的（或只标了对得上的一半）也算这组的；
    只回了一段的，就算名称写法不一样也是这组的。回了好几段、都标着别的行业场景时取不到（返回空），
    不能把别的场景的机会抄到这一行。"""

    texts = [
        (_labels(item), _clean(item.get("市场机会") or item.get("政策市场机会")))
        for item in items
        if isinstance(item, dict)
    ]
    texts = [(labels, text) for labels, text in texts if text]
    if len(texts) == 1:
        return texts[0][1]
    exact = [text for labels, text in texts if labels == (industry, scene)]
    if exact:
        return "\n\n".join(exact)
    compatible = [text for (ind, scn), text in texts if ind in ("", industry) and scn in ("", scene)]
    return "\n\n".join(compatible)


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
