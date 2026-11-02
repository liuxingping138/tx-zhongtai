"""新增场景补描述（打标任务 enrich）：交给模板的列、要模板输出的字段。

采纳进码表的新场景只有名称：给 AI 场景路径、所属行业、来源政策，以及上级场景的描述、同级几个已有场景的描述当范文，
让它照码表原有的写法写描述。写回码表标「待确认」，人在新增场景审核里核对。
"""

from __future__ import annotations

PATH_COLUMN = "场景路径"
# ai-service 的流水线靠每行的「源ID」把结果对回来，这里放场景路径
SOURCE_ID = "源ID"
COLUMNS: tuple[str, ...] = (SOURCE_ID, PATH_COLUMN, "新增级别", "所属行业", "来源政策", "上级场景描述", "同级场景示例")
DESC_90 = "场景描述90字"
DESC_130 = "场景描述130字"
DESC_PEST = "场景描述PEST"
LEVEL_DESC = "本级场景描述"
REQUIRED: tuple[str, ...] = (DESC_90,)
OPTIONAL: tuple[tuple[str, ...], ...] = ((DESC_130,), (DESC_PEST,), (LEVEL_DESC,))
# 输出字段 -> 码表里的列（codebook /internal/v1/scenarios/enrich 收的键）
FIELD_COLUMNS = {DESC_90: "desc_90", DESC_130: "desc_130", DESC_PEST: "desc_pest", LEVEL_DESC: "level_desc"}
LEVEL_NAMES = {1: "一级", 2: "二级", 3: "三级"}
NONE = "（没有）"
