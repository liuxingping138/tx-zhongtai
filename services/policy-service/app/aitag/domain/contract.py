"""打标任务和模板之间的约定：每个任务交给模板哪些列（模板里 @【列名】 能引用的）、要模板输出哪些字段。

提问配置页按它标出模板适不适合某个任务，任务设置选模板时按它拦下不合格的；
从数据库取测试数据也按它生成同样的列，测试输入和正式打标的输入一致。
"""

from __future__ import annotations

from collections.abc import Iterable

from app.aitag.domain.interpret_rules import ANSWER_FIELDS, SCENES_COLUMN
from app.aitag.domain.rules import PROMPT_COLUMNS, SOURCE_ID, TYPE_FIELD
from app.policy.domain.candidates import AI_COLUMNS, AI_PATHS, AI_REASON_FIELD, AI_SIMILAR_FIELD, AI_VERDICT_FIELD

# 模板里引用码表全文的变量，三个任务都能用。
CODE_VARIABLE = "上传码表"
BODY_COLUMN = "政策正文"

COLUMNS: dict[str, tuple[str, ...]] = {
    "type": (SOURCE_ID, *PROMPT_COLUMNS),
    "interpret": (SOURCE_ID, *PROMPT_COLUMNS),
    "opportunity": (SOURCE_ID, *PROMPT_COLUMNS, SCENES_COLUMN),
    "scenario": AI_COLUMNS,
}
# 少了这些输出字段，结果写不回表：类型判断靠「政策类型名称」，解读至少要一级行业和一级场景，市场机会要「市场机会」。
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "type": (TYPE_FIELD,),
    "interpret": ("一级行业", "一级场景"),
    "opportunity": ("市场机会",),
    "scenario": (AI_VERDICT_FIELD, AI_SIMILAR_FIELD),
}


def _optional_interpret_fields() -> tuple[tuple[str, ...], ...]:
    """解读表除了一级行业、一级场景还能写回的列。同一列的几种写法放一组，第一种是提示里说的名字。"""

    groups: dict[str, list[str]] = {}
    for name, column in ANSWER_FIELDS.items():
        groups.setdefault(column, []).append(name)
    required = set(REQUIRED_FIELDS["interpret"])
    return tuple(tuple(names) for names in groups.values() if not required & set(names))


# 提醒里最多点名几个没输出的字段，其余说「等 N 个」。
SHOWN_EMPTY_FIELDS = 4
# 没输出这些字段也能跑、能写回，只是表里对应的列空着：上线前说清楚，免得以为能顶替正在用的模板。
OPTIONAL_FIELDS: dict[str, tuple[tuple[str, ...], ...]] = {
    "type": (),
    "interpret": _optional_interpret_fields(),
    "opportunity": (),
    "scenario": ((AI_REASON_FIELD,),),
}


def _quoted(names: Iterable[str]) -> str:
    return "、".join(f"@【{name}】" for name in names)


def check_template(
    task: str, variables: list[str], output_fields: list[str], system_code: bool
) -> dict[str, list[str]]:
    """模板放到这个任务里跑有没有问题。errors 是跑了也写不回去、必须改的；warnings 是能跑但结果可能不理想的。"""

    columns = COLUMNS[task]
    errors: list[str] = []
    unknown = [name for name in dict.fromkeys(variables) if name not in columns and name != CODE_VARIABLE]
    if unknown:
        errors.append(f"用了这个任务不提供的列：{_quoted(unknown)}。能用的列：{_quoted(columns)}")
    missing = [name for name in REQUIRED_FIELDS[task] if name not in output_fields]
    if missing:
        errors.append(f"输出字段缺少：{'、'.join(missing)}，结果写不回表")
    warnings: list[str] = []
    empty = [group[0] for group in OPTIONAL_FIELDS[task] if not set(group) & set(output_fields)]
    if empty:
        more = len(empty) > SHOWN_EMPTY_FIELDS
        names = "、".join(empty[:SHOWN_EMPTY_FIELDS]) + (f"等 {len(empty)} 个字段" if more else "")
        warnings.append(f"没有输出{names}，写回时这些列会空着")
    if BODY_COLUMN in columns and BODY_COLUMN not in variables:
        warnings.append(f"没有用 @【{BODY_COLUMN}】，模型只看得到标题，判断会不准")
    if task == "scenario" and AI_PATHS not in variables:
        warnings.append(f"没有用 @【{AI_PATHS}】，模型看不到码表里这个行业下有哪些场景，找不出相似的")
    if task == "opportunity" and not {"行业", "一级行业"} & set(output_fields):
        warnings.append("没有输出「行业」「场景」：一条政策有几条市场机会时，分不清各是哪条解读行的")
    if task == "opportunity" and SCENES_COLUMN not in variables:
        warnings.append(
            f"没有用 @【{SCENES_COLUMN}】，模型不知道这条政策解读出了哪些行业场景，市场机会可能对不上解读行"
        )
    if CODE_VARIABLE in variables and not system_code:
        warnings.append("码表用的是上传的文件，定时任务按上线时冻结的那份跑；要和系统码表口径一致，请改选系统码表")
    return {"errors": errors, "warnings": warnings}
